"""Lightweight parent/watchdog entry point for the Task39 V3-7 worker.

This module is intentionally safe to import before spawning MPI: it imports no
solver, ``mpi4py``, ``petsc4py``, or V3-7 orchestration code.  Numerical setup
starts only in the child ``benchmarks.task039_v3_7_orchestration --worker``;
the parent delegates sampling and complete-process-tree termination to the
reviewed Task38 launcher.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.watchdog_process_control import terminate_process_tree
from src.io.execution_plan import ExecutionPlan
from src.io.input_validation import load_and_resolve
from src.runners.task038_launcher import _run_worker, _write_bootstrap


V3_7_PROFILE_ID = "task039.v3_7.hybrid_iterative.p6-h5.v1"
V3_7_WATCHDOG_AUTH_FLAG = "--launched-by-task038-watchdog"
V3_7_DIRECT_PRODUCER_SHA = "5bfab734a9ca053b69fa1f3f20d907aacbf8b07f"
V3_7_DIRECT_RUN_ROOT = Path(
    "results/task039_5nm_v3_1deg_s5_hybrid_direct_m480/"
    "task039_v3_hybrid_direct_p6h5_m480_mpi8__hybrid_direct__mpi8__M480/"
    "20260815T111156.797076Z"
)
V3_7_WARNING_GIB = 170.0
V3_7_CRITICAL_GIB = 195.0
V3_7_ABSOLUTE_HARD_BYTES = 224_000_000_000
V3_7_POLL_SECONDS = 0.25
V3_7_QEP_ONLY_WORKER_MODULE = "benchmarks.task039_qep_only"
V3_7_CANDIDATE_B_FLAG = "--candidate-b-only"
V3_7_CANDIDATE_C_FLAG = "--candidate-c-only"
V3_7_CANDIDATE_D_FLAG = "--candidate-d-only"
V3_7_CANDIDATE_D_QUALIFIED_FLAG = "--candidate-d-qualified"
V3_7_CANDIDATE_E_FLAG = "--candidate-e-side-only"
V3_8_CANDIDATE_D_QUALIFIED_METHOD = "hybrid_iterative_exact_side_case_qualification"
V5_H4_SETUP_ONLY_FLAG = "--v5-h4-setup-only"
V5_H4_SETUP_ONLY_METHOD = "task039_v5_h4_exact_side_setup_only"
V5_H4_BLR_SIDE_COMPONENT_FLAG = "--v5-h4-blr-side-component"
V5_H4_BLR_SIDE_COMPONENT_METHOD = "task039_v5_h4_mumps_blr_side_component"
V5_H4_BLR_PROFILE_FLAG = "--v5-h4-blr-profile"
V5_H4_BLR_DEFAULT_PROFILE = "mumps_blr_v5_h4"
V5_H4_BLR_PROFILE_CHOICES = (
    V5_H4_BLR_DEFAULT_PROFILE,
    "mumps_blr_v5_h4_1e3",
)
V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG = "--v5-h4-fixed-budget-bottom-component"
V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT_FLAG = "--v5-h4-fixed-budget-exact-spool-root"
V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_METHOD = (
    "task039_v5_h4_fixed_budget_bottom_component"
)
V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_PROFILE = (
    "task039.v5.h4.fixed_budget.bottom_side_component.v1"
)
V5_H4_FIXED_BUDGET = 32
V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG = "--v6-h4-post-compaction-setup-only"
V6_H4_EXACT_SPOOL_ROOT_FLAG = "--v6-h4-exact-spool-root"
V6_H4_POST_COMPACTION_SETUP_ONLY_METHOD = "task039_v6_h4_post_compaction_setup_only"
V6_H4_POST_COMPACTION_PROFILE_ID = (
    "task039.v6.h4.post_compaction.exact_side_setup_only.v1"
)
V6_H4_SETUP_THRESHOLD_BYTES = 45118258790
V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG = "--v7-h4-exact-side-limit-setup-only"
V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_METHOD = "task039_v7_h4_exact_side_limit_setup_only"
V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID = "task039.v7.h4.exact_side.limit_setup_only.v1"
V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES = 90236517581
V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG = "--v7-h4-exact-side-exact-spool-root"
V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG = "--v7-h4-exact-side-full-formal"
V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD = "task039_v7_h4_exact_side_full_formal"
V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID = "task039.v7.h4.exact_side.full_formal.v1"
V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES = 100262797312
V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS = 21600
V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS = 28800
V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG = "--v6-h4-port-modal-bottom-component"
V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG = "--v6-h4-port-modal-exact-spool-root"
V6_H4_PORT_MODAL_BOTTOM_COMPONENT_METHOD = "task039_v6_h4_port_modal_bottom_component"
V6_H4_PORT_MODAL_BOTTOM_COMPONENT_PROFILE = (
    "task039.v6.h4.port_modal.bottom_component.v1"
)
V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES = 23622320128
V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG = "--v7-h4-streamed-bottom-producer"
V7_STREAMED_PETROV_BOTTOM_PRODUCER_METHOD = "task039_v7_streamed_bottom_basis_producer"
V7_STREAMED_PETROV_BOTTOM_PRODUCER_PROFILE = (
    "task039.v7.streamed.bottom_basis_producer.v1"
)
V7_STREAMED_PETROV_HARD_STOP_BYTES = 100262797312
V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG = "--v7-h4-streamed-bottom-consumer"
V7_STREAMED_PETROV_BOTTOM_CONSUMER_METHOD = "task039_v7_streamed_bottom_petrov_consumer"
V7_STREAMED_PETROV_BOTTOM_CONSUMER_PROFILE = (
    "task039.v7.streamed.bottom_petrov_consumer.v1"
)
V7_STREAMED_PETROV_BOTTOM_CONSUMER_HARD_STOP_BYTES = 90236517581
V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_FLAG = (
    "--v7-h4-streamed-bottom-consumer-basis-manifest"
)
V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_SHA256_FLAG = (
    "--v7-h4-streamed-bottom-consumer-basis-manifest-sha256"
)
V7_STREAMED_PETROV_BOTTOM_CONSUMER_EXACT_SPOOL_ROOT_FLAG = (
    "--v7-h4-streamed-bottom-consumer-exact-spool-root"
)
V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG = "--v8-h4-layer-block-reconstruction"
V8_H4_LAYER_BLOCK_RECONSTRUCTION_METHOD = "task039_v8_h4_layer_block_reconstruction"
V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE = "task039.v8.h4.layer_block_reconstruction.v1"
V8_H4_LAYER_SWEEP_BOTTOM_FLAG = "--v8-h4-layer-sweep-bottom"
V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG = "--v8-h4-layer-sweep-exact-spool-root"
V8_H4_LAYER_SWEEP_BOTTOM_METHOD = "task039_v8_h4_layer_sweep_bottom"
V8_H4_LAYER_SWEEP_BOTTOM_PROFILE = "task039.v8.h4.layer_sweep.bottom_component.v1"
V8_H4_LAYER_SWEEP_BOTTOM_HARD_STOP_BYTES = 45 * 2**30
V9_H4_BARE_F_SIDE_FLAG = "--v9-h4-bare-f-full-side-diagnostic"
V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG = "--v9-h4-bare-f-full-side-exact-spool-root"
V9_H4_BARE_F_SIDE_METHOD = "task039_v9_h4_bare_f_full_side_diagnostic"
V9_H4_BARE_F_SIDE_PROFILE = "task039.v9.h4.bare_f_full_side.diagnostic.v1"
V9_H4_BARE_F_SIDE_HARD_STOP_BYTES = 45 * 2**30


def _validate_resolved_identity(
    payload: Mapping[str, Any],
    *,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v6_h4_post_compaction_setup_only: bool = False,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
) -> None:
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
    ):
        method = payload.get("method", {})
        if payload.get("model_id") != "task039_5nm_v4_1deg_s5_hybrid_iterative_m480":
            raise ValueError("V5 h4 component requires the fixed h4 model")
        if method.get("kind") != "hybrid_iterative":
            raise ValueError("V5 h4 component requires hybrid_iterative")
        return
    if payload.get("dimension") != 3 or payload.get("model_id") != (
        "task039_5nm_v3_1deg_s5_hybrid_direct_m480"
    ):
        raise ValueError("V3-7 requires the official 1-degree h5 Hybrid-direct model")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    boundary = payload.get("boundary")
    method = payload.get("method")
    execution = payload.get("execution")
    if not all(
        isinstance(section, Mapping)
        for section in (incidence, discretization, boundary, method, execution)
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
        (execution["warning_memory_gib"], V3_7_WARNING_GIB),
        (execution["terminate_memory_gib"], V3_7_CRITICAL_GIB),
        (execution["absolute_terminate_memory_bytes"], V3_7_ABSOLUTE_HARD_BYTES),
        (execution["require_zero_swap"], True),
    )
    if any(actual != required for actual, required in expected):
        raise ValueError("V3-7 official physical/discrete identity is not exact")
    inventory = payload.get("derived", {}).get("external_mode_inventory", {})
    keys = inventory.get("keys") if isinstance(inventory, Mapping) else None
    if not isinstance(keys, list) or len(keys) != 600:
        raise ValueError("V3-7 requires the exact 600-key external inventory")


def _watchdog_policy(
    payload: Mapping[str, Any],
    *,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v6_h4_post_compaction_setup_only: bool = False,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
) -> dict[str, Any]:
    _validate_resolved_identity(
        payload,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
    )
    if v7_h4_exact_side_full_formal:
        absolute_bytes = V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
    elif v7_h4_exact_side_limit_setup_only:
        absolute_bytes = V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES
    elif v6_h4_post_compaction_setup_only:
        absolute_bytes = V6_H4_SETUP_THRESHOLD_BYTES
    elif v6_h4_port_modal_bottom_only:
        absolute_bytes = V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES
    elif v7_h4_streamed_bottom_producer:
        absolute_bytes = V7_STREAMED_PETROV_HARD_STOP_BYTES
    elif v7_h4_streamed_bottom_consumer:
        absolute_bytes = V7_STREAMED_PETROV_BOTTOM_CONSUMER_HARD_STOP_BYTES
    elif v8_h4_layer_sweep_bottom:
        absolute_bytes = V8_H4_LAYER_SWEEP_BOTTOM_HARD_STOP_BYTES
    elif v9_h4_bare_f_side:
        absolute_bytes = V9_H4_BARE_F_SIDE_HARD_STOP_BYTES
    else:
        absolute_bytes = V3_7_ABSOLUTE_HARD_BYTES
    policy = {
        "warning_memory_gib": V3_7_WARNING_GIB,
        "critical_memory_gib": V3_7_CRITICAL_GIB,
        "critical_action": "record_checkpoint_only",
        "absolute_terminate_memory_bytes": absolute_bytes,
        "absolute_hard_stop_action": "terminate_complete_process_tree",
        "require_zero_swap": True,
        "poll_interval_seconds": V3_7_POLL_SECONDS,
        "hard_stop_gib": absolute_bytes / 2**30,
    }
    if v8_h4_layer_block_reconstruction:
        policy["profile"] = V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE
    if v8_h4_layer_sweep_bottom:
        policy["profile"] = V8_H4_LAYER_SWEEP_BOTTOM_PROFILE
    if v9_h4_bare_f_side:
        policy["profile"] = V9_H4_BARE_F_SIDE_PROFILE
    if v7_h4_exact_side_full_formal:
        policy["timeout_policy"] = {
            "default_seconds": V7_H4_EXACT_SIDE_FULL_FORMAL_DEFAULT_TIMEOUT_SECONDS,
            "conditional_extension_seconds": (
                V7_H4_EXACT_SIDE_FULL_FORMAL_EXTENSION_TIMEOUT_SECONDS
            ),
            "extension_requires_outer_and_decreasing_residual": True,
            "automatic_extension": False,
        }
    return policy


def _check_direct_producer(run_root: Path) -> None:
    manifest_path = run_root.resolve() / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"V3-7 direct producer manifest is unavailable: {run_root}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V3-7 direct producer manifest is unreadable") from exc
    if not isinstance(manifest, Mapping) or any(
        (
            manifest.get("model_id") != "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
            manifest.get("method") != "hybrid_direct",
            manifest.get("mpi_size") != 8,
            manifest.get("source_sha") != V3_7_DIRECT_PRODUCER_SHA,
        )
    ):
        raise ValueError(
            "V3-7 direct producer identity is not the fixed h5/M480/MPI8 run"
        )


def load_v3_7_official_payload(
    input_path: str | Path,
    *,
    v5_h4_setup_only: bool = False,
    v5_h4_blr_side_only: bool = False,
    v5_h4_fixed_budget_bottom_only: bool = False,
    v6_h4_post_compaction_setup_only: bool = False,
    v7_h4_exact_side_limit_setup_only: bool = False,
    v7_h4_exact_side_full_formal: bool = False,
    v6_h4_port_modal_bottom_only: bool = False,
    v7_h4_streamed_bottom_producer: bool = False,
    v7_h4_streamed_bottom_consumer: bool = False,
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
) -> dict[str, Any]:
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
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
    ):
        from benchmarks.task039_v4_h4_hybrid_direct import (
            validate_v4_h4_specification,
        )

        validate_v4_h4_specification(specification)
    _validate_resolved_identity(
        payload,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
    )
    return payload


def build_v3_7_execution_plan(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    qep_only: bool = False,
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
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = V5_H4_BLR_DEFAULT_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the explicit MPI8 child argv without importing the worker."""

    payload = load_v3_7_official_payload(
        input_path,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
    )
    if v5_h4_blr_side_only and v5_h4_blr_profile not in V5_H4_BLR_PROFILE_CHOICES:
        raise ValueError(f"Unsupported V5 h4 BLR profile: {v5_h4_blr_profile}")
    policy = _watchdog_policy(
        payload,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
    )
    executable = str(Path(os.path.abspath(python_executable or sys.executable)))
    mpiexec = mpiexec_command or shutil.which("mpiexec") or "mpiexec"
    if (
        sum(
            (
                bool(qep_only),
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
            )
        )
        > 1
    ):
        raise ValueError(
            "QEP-only, candidate, and V5 h4 component routes are exclusive"
        )
    worker_module = (
        V3_7_QEP_ONLY_WORKER_MODULE
        if qep_only
        else "benchmarks.task039_v3_7_orchestration"
    )
    argv = [
        str(mpiexec),
        "-n",
        "8",
        executable,
        "-m",
        worker_module,
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
        argv.append(V3_7_CANDIDATE_B_FLAG)
    if candidate_c_only:
        argv.append(V3_7_CANDIDATE_C_FLAG)
    if candidate_d_only:
        argv.append(V3_7_CANDIDATE_D_FLAG)
    if candidate_d_qualified:
        argv.append(V3_7_CANDIDATE_D_QUALIFIED_FLAG)
    if candidate_e_side_only:
        argv.append(V3_7_CANDIDATE_E_FLAG)
    if v5_h4_setup_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
            )
        ):
            raise ValueError("V5 h4 setup-only requires the shared packet arguments")
        argv.extend(
            [
                V5_H4_SETUP_ONLY_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
            ]
        )
    elif v5_h4_blr_side_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
            )
        ):
            raise ValueError(
                "V5 h4 BLR side component requires the shared packet arguments"
            )
        argv.extend(
            [
                V5_H4_BLR_SIDE_COMPONENT_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
            ]
        )
        if v5_h4_blr_profile != V5_H4_BLR_DEFAULT_PROFILE:
            argv.extend([V5_H4_BLR_PROFILE_FLAG, v5_h4_blr_profile])
    elif v5_h4_fixed_budget_bottom_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v5_h4_fixed_budget_exact_spool_root,
            )
        ):
            raise ValueError(
                "V5 fixed-budget component requires packet and exact spool arguments"
            )
        argv.extend(
            [
                V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v5_h4_fixed_budget_exact_spool_root).resolve()),
            ]
        )
    elif v7_h4_exact_side_full_formal:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v7_h4_exact_side_exact_spool_root,
            )
        ):
            raise ValueError("V7 full formal requires packet and exact spool arguments")
        argv.extend(
            [
                V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v7_h4_exact_side_exact_spool_root).resolve()),
            ]
        )
    elif v7_h4_exact_side_limit_setup_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v7_h4_exact_side_exact_spool_root,
            )
        ):
            raise ValueError(
                "V7 exact-side setup requires packet and exact spool arguments"
            )
        argv.extend(
            [
                V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v7_h4_exact_side_exact_spool_root).resolve()),
            ]
        )
    elif v6_h4_post_compaction_setup_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v6_h4_exact_spool_root,
            )
        ):
            raise ValueError("V6 setup requires packet and exact spool arguments")
        argv.extend(
            [
                V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V6_H4_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v6_h4_exact_spool_root).resolve()),
            ]
        )
    elif v6_h4_port_modal_bottom_only:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v6_h4_port_modal_exact_spool_root,
            )
        ):
            raise ValueError(
                "V6 port-modal component requires packet and exact spool arguments"
            )
        argv.extend(
            [
                V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v6_h4_port_modal_exact_spool_root).resolve()),
            ]
        )
    elif v7_h4_streamed_bottom_producer:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
            )
        ):
            raise ValueError(
                "V7 streamed producer requires the shared packet arguments"
            )
        argv.extend(
            [
                V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
            ]
        )
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
                "V7 streamed consumer requires shared packet, basis manifest, "
                "and exact spool arguments"
            )
        argv.extend(
            [
                V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_FLAG,
                str(Path(v7_h4_streamed_bottom_consumer_basis_manifest).resolve()),
                V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_SHA256_FLAG,
                str(v7_h4_streamed_bottom_consumer_basis_manifest_sha256),
                V7_STREAMED_PETROV_BOTTOM_CONSUMER_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v7_h4_streamed_bottom_consumer_exact_spool_root).resolve()),
            ]
        )
    elif v8_h4_layer_block_reconstruction:
        argv.append(V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG)
    elif v8_h4_layer_sweep_bottom:
        if not all(
            (
                selected_mode_packet_manifest,
                selected_mode_packet_identity,
                selected_mode_packet_manifest_sha256,
                v8_h4_layer_sweep_exact_spool_root,
            )
        ):
            raise ValueError(
                "V8 layer sweep requires packet identity and exact spool arguments"
            )
        argv.extend(
            [
                V8_H4_LAYER_SWEEP_BOTTOM_FLAG,
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
                V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v8_h4_layer_sweep_exact_spool_root).resolve()),
            ]
        )
    elif v9_h4_bare_f_side:
        if v9_h4_bare_f_side_exact_spool_root is None:
            raise ValueError("V9 bare-F route requires the exact spool root")
        argv.extend(
            [
                V9_H4_BARE_F_SIDE_FLAG,
                V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG,
                str(Path(v9_h4_bare_f_side_exact_spool_root).resolve()),
            ]
        )
    if candidate_d_qualified:
        method = V3_8_CANDIDATE_D_QUALIFIED_METHOD
    elif candidate_d_only:
        method = "USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D"
    elif candidate_e_side_only:
        method = "hybrid_iterative_candidate_e_side_only"
    elif v7_h4_exact_side_full_formal:
        method = V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD
    elif v7_h4_exact_side_limit_setup_only:
        method = V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_METHOD
    elif v6_h4_post_compaction_setup_only:
        method = V6_H4_POST_COMPACTION_SETUP_ONLY_METHOD
    elif v6_h4_port_modal_bottom_only:
        method = V6_H4_PORT_MODAL_BOTTOM_COMPONENT_METHOD
    elif v7_h4_streamed_bottom_producer:
        method = V7_STREAMED_PETROV_BOTTOM_PRODUCER_METHOD
    elif v7_h4_streamed_bottom_consumer:
        method = V7_STREAMED_PETROV_BOTTOM_CONSUMER_METHOD
    elif v8_h4_layer_block_reconstruction:
        method = V8_H4_LAYER_BLOCK_RECONSTRUCTION_METHOD
    elif v8_h4_layer_sweep_bottom:
        method = V8_H4_LAYER_SWEEP_BOTTOM_METHOD
    elif v9_h4_bare_f_side:
        method = V9_H4_BARE_F_SIDE_METHOD
    elif v5_h4_setup_only:
        method = V5_H4_SETUP_ONLY_METHOD
    elif v5_h4_blr_side_only:
        method = V5_H4_BLR_SIDE_COMPONENT_METHOD
    elif v5_h4_fixed_budget_bottom_only:
        method = V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_METHOD
    elif candidate_c_only:
        method = "hybrid_iterative_candidate_c1_only"
    elif candidate_b_only:
        method = "hybrid_iterative_candidate_b_only"
    elif qep_only:
        method = "positive_branch_qep_only"
    else:
        method = "hybrid_iterative_v3_7_diagnostic"
    if v7_h4_exact_side_full_formal:
        profile_id = V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID
    elif v7_h4_exact_side_limit_setup_only:
        profile_id = V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID
    elif v6_h4_post_compaction_setup_only:
        profile_id = V6_H4_POST_COMPACTION_PROFILE_ID
    elif v6_h4_port_modal_bottom_only:
        profile_id = V6_H4_PORT_MODAL_BOTTOM_COMPONENT_PROFILE
    elif v7_h4_streamed_bottom_producer:
        profile_id = V7_STREAMED_PETROV_BOTTOM_PRODUCER_PROFILE
    elif v7_h4_streamed_bottom_consumer:
        profile_id = V7_STREAMED_PETROV_BOTTOM_CONSUMER_PROFILE
    elif v8_h4_layer_block_reconstruction:
        profile_id = V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE
    elif v8_h4_layer_sweep_bottom:
        profile_id = V8_H4_LAYER_SWEEP_BOTTOM_PROFILE
    elif v9_h4_bare_f_side:
        profile_id = V9_H4_BARE_F_SIDE_PROFILE
    elif v5_h4_setup_only:
        profile_id = "task039.v5.h4.exact-side.setup-only.v1"
    elif v5_h4_blr_side_only:
        profile_id = "task039.v5.h4.mumps_blr.side_component.v1"
    elif v5_h4_fixed_budget_bottom_only:
        profile_id = V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_PROFILE
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
    elif v8_h4_layer_sweep_bottom and v8_h4_layer_sweep_exact_spool_root is not None:
        exact_spool_root = str(Path(v8_h4_layer_sweep_exact_spool_root).resolve())
    elif v9_h4_bare_f_side and v9_h4_bare_f_side_exact_spool_root is not None:
        exact_spool_root = str(Path(v9_h4_bare_f_side_exact_spool_root).resolve())
    elif v7_h4_streamed_bottom_producer:
        exact_spool_root = None
    elif (
        v7_h4_streamed_bottom_consumer
        and v7_h4_streamed_bottom_consumer_exact_spool_root is not None
    ):
        exact_spool_root = str(
            Path(v7_h4_streamed_bottom_consumer_exact_spool_root).resolve()
        )
    elif (
        v5_h4_fixed_budget_bottom_only
        and v5_h4_fixed_budget_exact_spool_root is not None
    ):
        exact_spool_root = str(Path(v5_h4_fixed_budget_exact_spool_root).resolve())
    else:
        exact_spool_root = None
    return {
        "argv": argv,
        "shell": False,
        "launcher": "benchmarks.task039_v3_7_watchdog -> src.runners.task038_launcher",
        "watchdog": policy,
        "worker_contract": {
            "mpi_size": 8,
            "profile_id": profile_id,
            "method": method,
            "mumps_blr_profile": (v5_h4_blr_profile if v5_h4_blr_side_only else None),
            "fixed_budget": (
                V5_H4_FIXED_BUDGET if v5_h4_fixed_budget_bottom_only else None
            ),
            "exact_spool_root": exact_spool_root,
            "basis_manifest": (
                str(Path(v7_h4_streamed_bottom_consumer_basis_manifest).resolve())
                if v7_h4_streamed_bottom_consumer_basis_manifest is not None
                else None
            ),
            "basis_manifest_sha256": (
                v7_h4_streamed_bottom_consumer_basis_manifest_sha256
            ),
            "absolute_terminate_memory_bytes": policy[
                "absolute_terminate_memory_bytes"
            ],
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
    qep_only: bool = False,
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
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = V5_H4_BLR_DEFAULT_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    plan = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        qep_only=qep_only,
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
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
        v9_h4_bare_f_side_exact_spool_root=v9_h4_bare_f_side_exact_spool_root,
        v7_h4_streamed_bottom_consumer_basis_manifest=(
            v7_h4_streamed_bottom_consumer_basis_manifest
        ),
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256
        ),
        v7_h4_streamed_bottom_consumer_exact_spool_root=(
            v7_h4_streamed_bottom_consumer_exact_spool_root
        ),
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
        v8_h4_layer_sweep_exact_spool_root=v8_h4_layer_sweep_exact_spool_root,
        v5_h4_blr_profile=v5_h4_blr_profile,
        selected_mode_packet_manifest=selected_mode_packet_manifest,
        selected_mode_packet_identity=selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=selected_mode_packet_manifest_sha256,
    )
    if plan["argv"][1:3] != ["-n", "8"]:
        raise ValueError("V3-7 execution plan is not fixed to MPI8")
    return plan


def launch_v3_7_with_task038_watchdog(
    input_path: str | Path,
    run_directory: str | Path,
    *,
    source_sha: str,
    python_executable: str | Path | None = None,
    mpiexec_command: str | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
    sample_factory: Callable[[int], dict[str, Any]] = resource_authority_sample,
    terminate_factory: Callable[[Any], dict[str, Any]] = terminate_process_tree,
    qep_only: bool = False,
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
    v8_h4_layer_block_reconstruction: bool = False,
    v8_h4_layer_sweep_bottom: bool = False,
    v9_h4_bare_f_side: bool = False,
    v9_h4_bare_f_side_exact_spool_root: str | Path | None = None,
    v8_h4_layer_sweep_exact_spool_root: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest: str | Path | None = None,
    v7_h4_streamed_bottom_consumer_basis_manifest_sha256: str | None = None,
    v7_h4_streamed_bottom_consumer_exact_spool_root: str | Path | None = None,
    v5_h4_blr_profile: str = V5_H4_BLR_DEFAULT_PROFILE,
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run one authenticated V3-7 child through Task38's watchdog."""

    load_v3_7_official_payload(
        input_path,
        v5_h4_setup_only=v5_h4_setup_only,
        v5_h4_blr_side_only=v5_h4_blr_side_only,
        v5_h4_fixed_budget_bottom_only=v5_h4_fixed_budget_bottom_only,
        v6_h4_post_compaction_setup_only=v6_h4_post_compaction_setup_only,
        v7_h4_exact_side_limit_setup_only=v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_full_formal=v7_h4_exact_side_full_formal,
        v6_h4_port_modal_bottom_only=v6_h4_port_modal_bottom_only,
        v7_h4_streamed_bottom_producer=v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
    )
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
    ):
        _check_direct_producer(V3_7_DIRECT_RUN_ROOT)
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha.lower()
    ):
        raise ValueError("V3-7 source_sha must be a full hexadecimal commit SHA")
    specification = load_and_resolve(input_path)
    plan_payload = build_v3_7_execution_plan(
        input_path,
        run_directory,
        source_sha=source_sha,
        python_executable=python_executable,
        mpiexec_command=mpiexec_command,
        qep_only=qep_only,
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
        v8_h4_layer_block_reconstruction=v8_h4_layer_block_reconstruction,
        v9_h4_bare_f_side=v9_h4_bare_f_side,
        v9_h4_bare_f_side_exact_spool_root=v9_h4_bare_f_side_exact_spool_root,
        v7_h4_streamed_bottom_consumer_basis_manifest=(
            v7_h4_streamed_bottom_consumer_basis_manifest
        ),
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256
        ),
        v7_h4_streamed_bottom_consumer_exact_spool_root=(
            v7_h4_streamed_bottom_consumer_exact_spool_root
        ),
        v8_h4_layer_sweep_bottom=v8_h4_layer_sweep_bottom,
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
    start_time = datetime.now(timezone.utc).isoformat()
    manifest, _resolved_sha = _write_bootstrap(
        specification,
        run_dir,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_watchdog",
        start_time=start_time,
    )
    executable = Path(os.path.abspath(python_executable or sys.executable))
    plan = ExecutionPlan(
        argv=tuple(plan_payload["argv"]),
        shell=False,
        executable=executable,
        worker_module=plan_payload["argv"][5],
        method=plan_payload["worker_contract"]["method"],
        mpi_size=8,
        requested_modes=480,
        physical_model_sha256=specification.physical_model_sha256,
        input_sha256=specification.input_sha256,
        source_sha=source_sha,
        adapter_identity="task039.v3_7_watchdog",
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
        popen_factory=popen_factory,
        sample_factory=sample_factory,
        terminate_factory=terminate_factory,
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
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"run_directory": str(run_dir), **result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--python-executable")
    parser.add_argument("--mpiexec-command")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qep-only", action="store_true")
    parser.add_argument("--candidate-b-only", action="store_true")
    parser.add_argument("--candidate-c-only", action="store_true")
    parser.add_argument("--candidate-d-only", action="store_true")
    parser.add_argument("--candidate-d-qualified", action="store_true")
    parser.add_argument("--candidate-e-side-only", action="store_true")
    parser.add_argument("--v5-h4-setup-only", action="store_true")
    parser.add_argument(V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG, action="store_true")
    parser.add_argument(V6_H4_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG, action="store_true")
    parser.add_argument(V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG, action="store_true")
    parser.add_argument(V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG, action="store_true")
    parser.add_argument(V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG, action="store_true")
    parser.add_argument(V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG, action="store_true")
    parser.add_argument(V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG, action="store_true")
    parser.add_argument(V8_H4_LAYER_SWEEP_BOTTOM_FLAG, action="store_true")
    parser.add_argument(V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(
        V9_H4_BARE_F_SIDE_FLAG,
        dest="v9_h4_bare_f_side",
        action="store_true",
    )
    parser.add_argument(
        V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG,
        dest="v9_h4_bare_f_side_exact_spool_root",
    )
    parser.add_argument(V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_FLAG)
    parser.add_argument(V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_SHA256_FLAG)
    parser.add_argument(V7_STREAMED_PETROV_BOTTOM_CONSUMER_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(V5_H4_BLR_SIDE_COMPONENT_FLAG, action="store_true")
    parser.add_argument(V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG, action="store_true")
    parser.add_argument(V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT_FLAG)
    parser.add_argument(
        V5_H4_BLR_PROFILE_FLAG,
        choices=V5_H4_BLR_PROFILE_CHOICES,
        default=V5_H4_BLR_DEFAULT_PROFILE,
    )
    parser.add_argument("--selected-mode-packet-manifest")
    parser.add_argument("--selected-mode-packet-identity")
    parser.add_argument("--selected-mode-packet-manifest-sha256")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(
            json.dumps(
                v3_7_execution_dry_run(
                    args.input,
                    args.run_directory,
                    source_sha=args.source_sha,
                    python_executable=args.python_executable,
                    qep_only=args.qep_only,
                    candidate_b_only=args.candidate_b_only,
                    candidate_c_only=args.candidate_c_only,
                    candidate_d_only=args.candidate_d_only,
                    candidate_d_qualified=args.candidate_d_qualified,
                    candidate_e_side_only=args.candidate_e_side_only,
                    v5_h4_setup_only=args.v5_h4_setup_only,
                    v5_h4_blr_side_only=args.v5_h4_blr_side_component,
                    v5_h4_fixed_budget_bottom_only=(
                        args.v5_h4_fixed_budget_bottom_component
                    ),
                    v5_h4_fixed_budget_exact_spool_root=(
                        args.v5_h4_fixed_budget_exact_spool_root
                    ),
                    v6_h4_post_compaction_setup_only=(
                        args.v6_h4_post_compaction_setup_only
                    ),
                    v6_h4_exact_spool_root=args.v6_h4_exact_spool_root,
                    v7_h4_exact_side_limit_setup_only=(
                        args.v7_h4_exact_side_limit_setup_only
                    ),
                    v7_h4_exact_side_exact_spool_root=(
                        args.v7_h4_exact_side_exact_spool_root
                    ),
                    v6_h4_port_modal_bottom_only=args.v6_h4_port_modal_bottom_component,
                    v6_h4_port_modal_exact_spool_root=(
                        args.v6_h4_port_modal_exact_spool_root
                    ),
                    v7_h4_exact_side_full_formal=args.v7_h4_exact_side_full_formal,
                    v7_h4_streamed_bottom_producer=args.v7_h4_streamed_bottom_producer,
                    v7_h4_streamed_bottom_consumer=(
                        args.v7_h4_streamed_bottom_consumer
                    ),
                    v8_h4_layer_block_reconstruction=(
                        args.v8_h4_layer_block_reconstruction
                    ),
                    v8_h4_layer_sweep_bottom=args.v8_h4_layer_sweep_bottom,
                    v9_h4_bare_f_side=args.v9_h4_bare_f_side,
                    v9_h4_bare_f_side_exact_spool_root=(
                        args.v9_h4_bare_f_side_exact_spool_root
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
                    v5_h4_blr_profile=args.v5_h4_blr_profile,
                    selected_mode_packet_manifest=args.selected_mode_packet_manifest,
                    selected_mode_packet_identity=args.selected_mode_packet_identity,
                    selected_mode_packet_manifest_sha256=args.selected_mode_packet_manifest_sha256,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    result = launch_v3_7_with_task038_watchdog(
        args.input,
        args.run_directory,
        source_sha=args.source_sha,
        python_executable=args.python_executable,
        mpiexec_command=args.mpiexec_command,
        qep_only=args.qep_only,
        candidate_b_only=args.candidate_b_only,
        candidate_c_only=args.candidate_c_only,
        candidate_d_only=args.candidate_d_only,
        candidate_d_qualified=args.candidate_d_qualified,
        candidate_e_side_only=args.candidate_e_side_only,
        v5_h4_setup_only=args.v5_h4_setup_only,
        v5_h4_blr_side_only=args.v5_h4_blr_side_component,
        v5_h4_fixed_budget_bottom_only=(args.v5_h4_fixed_budget_bottom_component),
        v5_h4_fixed_budget_exact_spool_root=(args.v5_h4_fixed_budget_exact_spool_root),
        v6_h4_post_compaction_setup_only=args.v6_h4_post_compaction_setup_only,
        v6_h4_exact_spool_root=args.v6_h4_exact_spool_root,
        v7_h4_exact_side_limit_setup_only=args.v7_h4_exact_side_limit_setup_only,
        v7_h4_exact_side_exact_spool_root=args.v7_h4_exact_side_exact_spool_root,
        v6_h4_port_modal_bottom_only=args.v6_h4_port_modal_bottom_component,
        v6_h4_port_modal_exact_spool_root=args.v6_h4_port_modal_exact_spool_root,
        v7_h4_exact_side_full_formal=args.v7_h4_exact_side_full_formal,
        v7_h4_streamed_bottom_producer=args.v7_h4_streamed_bottom_producer,
        v7_h4_streamed_bottom_consumer=args.v7_h4_streamed_bottom_consumer,
        v8_h4_layer_block_reconstruction=args.v8_h4_layer_block_reconstruction,
        v8_h4_layer_sweep_bottom=args.v8_h4_layer_sweep_bottom,
        v9_h4_bare_f_side=args.v9_h4_bare_f_side,
        v9_h4_bare_f_side_exact_spool_root=(args.v9_h4_bare_f_side_exact_spool_root),
        v8_h4_layer_sweep_exact_spool_root=(args.v8_h4_layer_sweep_exact_spool_root),
        v7_h4_streamed_bottom_consumer_basis_manifest=(
            args.v7_h4_streamed_bottom_consumer_basis_manifest
        ),
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256=(
            args.v7_h4_streamed_bottom_consumer_basis_manifest_sha256
        ),
        v7_h4_streamed_bottom_consumer_exact_spool_root=(
            args.v7_h4_streamed_bottom_consumer_exact_spool_root
        ),
        v5_h4_blr_profile=args.v5_h4_blr_profile,
        selected_mode_packet_manifest=args.selected_mode_packet_manifest,
        selected_mode_packet_identity=args.selected_mode_packet_identity,
        selected_mode_packet_manifest_sha256=args.selected_mode_packet_manifest_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("exit_status") == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "V3_7_ABSOLUTE_HARD_BYTES",
    "V3_7_DIRECT_RUN_ROOT",
    "V3_7_CANDIDATE_C_FLAG",
    "V3_7_CANDIDATE_D_FLAG",
    "V3_7_CANDIDATE_D_QUALIFIED_FLAG",
    "V3_7_CANDIDATE_E_FLAG",
    "V3_7_QEP_ONLY_WORKER_MODULE",
    "V3_8_CANDIDATE_D_QUALIFIED_METHOD",
    "V5_H4_BLR_SIDE_COMPONENT_FLAG",
    "V5_H4_BLR_SIDE_COMPONENT_METHOD",
    "V5_H4_BLR_PROFILE_FLAG",
    "V5_H4_BLR_DEFAULT_PROFILE",
    "V5_H4_BLR_PROFILE_CHOICES",
    "V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG",
    "V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT_FLAG",
    "V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_METHOD",
    "V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_PROFILE",
    "V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG",
    "V6_H4_EXACT_SPOOL_ROOT_FLAG",
    "V6_H4_POST_COMPACTION_SETUP_ONLY_METHOD",
    "V6_H4_POST_COMPACTION_PROFILE_ID",
    "V6_H4_SETUP_THRESHOLD_BYTES",
    "V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG",
    "V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_METHOD",
    "V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID",
    "V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES",
    "V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG",
    "V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG",
    "V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD",
    "V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID",
    "V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES",
    "V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG",
    "V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG",
    "V6_H4_PORT_MODAL_BOTTOM_COMPONENT_METHOD",
    "V6_H4_PORT_MODAL_BOTTOM_COMPONENT_PROFILE",
    "V6_H4_PORT_MODAL_CONSTRUCTION_HARD_STOP_BYTES",
    "V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG",
    "V7_STREAMED_PETROV_BOTTOM_PRODUCER_METHOD",
    "V7_STREAMED_PETROV_BOTTOM_PRODUCER_PROFILE",
    "V7_STREAMED_PETROV_HARD_STOP_BYTES",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_METHOD",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_PROFILE",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_HARD_STOP_BYTES",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_FLAG",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_BASIS_MANIFEST_SHA256_FLAG",
    "V7_STREAMED_PETROV_BOTTOM_CONSUMER_EXACT_SPOOL_ROOT_FLAG",
    "V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG",
    "V8_H4_LAYER_BLOCK_RECONSTRUCTION_METHOD",
    "V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE",
    "V8_H4_LAYER_SWEEP_BOTTOM_FLAG",
    "V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG",
    "V8_H4_LAYER_SWEEP_BOTTOM_METHOD",
    "V8_H4_LAYER_SWEEP_BOTTOM_PROFILE",
    "V8_H4_LAYER_SWEEP_BOTTOM_HARD_STOP_BYTES",
    "V9_H4_BARE_F_SIDE_FLAG",
    "V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG",
    "V9_H4_BARE_F_SIDE_METHOD",
    "V9_H4_BARE_F_SIDE_PROFILE",
    "V9_H4_BARE_F_SIDE_HARD_STOP_BYTES",
    "build_v3_7_execution_plan",
    "launch_v3_7_with_task038_watchdog",
    "load_v3_7_official_payload",
    "main",
    "v3_7_execution_dry_run",
]
