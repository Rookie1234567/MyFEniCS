"""Thin Task040 Level-A process-tree watchdog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.task034_wsl_resources import (
    resource_authority_sample,
    wsl_memory_snapshot,
)
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_HARD_STOP_BYTES as _TASK040_LEVEL_A_HARD_STOP_BYTES,
)
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_MPI_SIZE,
    TASK040_LEVEL_A_THREADS,
    TASK040_LEVEL_A_TIMEOUT_SECONDS,
    TASK040_V1_1_SCALAR_KRYLOV_FLAG,
    TASK040_V1_2_INTERFACE_SCHUR_FLAG,
    TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
    TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG,
    TASK040_V3_2_COUPLED_INTERFACE_FLAG,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG,
    TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG,
    TASK040_V5_ROUTE_C_FLAG,
    TASK040_V6_2_INTERFACE_SCHUR_FLAG,
    V7_MOVING_PML_FULL_STATE_FLAG,
    V7_SCALE_NORMALIZED_IDENTITY_FLAG,
    V8_ADAPTIVE_HARD_STOP_BYTES,
    V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
    V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
    V8_ADAPTIVE_SCHWARZ_ONLY_FLAG,
    V8_ADAPTIVE_SETUP_TARGET_SECONDS,
    V8_ADAPTIVE_STAGE_B1_ONLY_FLAG,
    V8_ADAPTIVE_STAGE_BC_ONLY_FLAG,
    V8_ADAPTIVE_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
    V8_FULL_SPECTRUM_ONLY_FLAG,
    V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
    V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
    V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
    V9_C0_EXPLICIT_COARSE_ONLY_FLAG,
    V9_C0_EXPLICIT_COARSE_ONLY_SCHEMA,
    V9_C0_HARD_STOP_BYTES,
    V9_C0_MARKER_SEQUENCE,
    V9_C0_MIN_AVAILABLE_BYTES,
    V9_C0_ONE_APPLY_TARGET_SECONDS,
    V9_C0_PREFERRED_MEMORY_BYTES,
    V9_C0_SETUP_TARGET_SECONDS,
    V9_C0_TIMEOUT_SECONDS,
    V9_C0_WARNING_MEMORY_BYTES,
    V9_E_LOR_L2_MARKER_SEQUENCE,
    V9_E_LOR_L2_ONLY_FLAG,
    V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
    V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
    V9_E_S3_B1_MARKER_SEQUENCE,
    V9_E_S3_B1_SCHEMA,
    V9_E_S3_J1_BASELINE_MANIFEST_OPTION,
    V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION,
    V9_E_S3_J1_BASELINE_ONLY_FLAG,
    V9_E_S3_J1_BASELINE_SCHEMA,
    V9_E_S3_MARKER_SEQUENCE,
    V9_E_S3_STRUCTURED_B1_ONLY_FLAG,
    V9_SOURCE_BRIDGE_ONLY_FLAG,
    V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION,
    V9_SOURCE_PACKET_ROOT_OPTION,
    build_task040_level_a_plan,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from src.solvers.floquet_background_hcurl_s3_pilot import (
    S3B_CONDITIONAL_NOT_QUALIFIED,
    S3B_CONDITIONAL_UNSTABLE,
    S3B_FIVE_SOURCE_NO_SIGNAL,
    S3B_FIVE_SOURCE_PASS,
    S3B_FIVE_SOURCE_UNSTABLE,
    S3B_INITIAL_NO_SIGNAL,
    S3B_INITIAL_UNSTABLE,
    S3B_NEXT_FACTOR_FREE_PRODUCTIONIZATION,
    S3B_NEXT_FIXED_LOR,
)

ROOT = Path(__file__).resolve().parents[1]
TASK040_LEVEL_A_HARD_STOP_BYTES = _TASK040_LEVEL_A_HARD_STOP_BYTES
SAMPLE_INTERVAL_SECONDS = 0.5
HEARTBEAT_SECONDS = 60.0
SWAP_LIMIT_BYTES = 0
V8_RESOURCE_UNAVAILABLE_CLASSIFICATION = (
    "FULL_SPECTRUM_CURRENT_IMPLEMENTATION_RESOURCE_UNAVAILABLE"
)
V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION = (
    "ADAPTIVE_IMPEDANCE_STAGE_A_RESOURCE_UNAVAILABLE"
)
V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION = (
    "ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE"
)
V9_C0_NEXT_C1 = "V9_C1_MATRIX_FREE_GALERKIN_COARSE"
V9_C0_NEXT_E = "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"
_TERMINAL_CLEANUP_STAGES = frozenset(
    {
        "cleanup",
        "v4_identity_stop",
        "v5_route_c_cleanup",
        "v6_2_cleanup",
        "v7_moving_pml_cleanup",
        "v8_full_spectrum_cleanup_complete",
        "v8_adaptive_cleanup_complete",
        "v8_adaptive_stage_b1_cleanup_complete",
        "v8_adaptive_stage_bc_cleanup_complete",
        "v9_source_bridge_cleanup_complete",
        "v9_c0_cleanup_complete",
        "v9_e_lor_l2_cleanup_complete",
        "s3b_j1_cleanup_complete",
        "s3b_b1_cleanup_complete",
    }
)
_S3_CANDIDATE_TERMINAL_NEXT_STAGES = {
    S3B_INITIAL_NO_SIGNAL: S3B_NEXT_FIXED_LOR,
    S3B_INITIAL_UNSTABLE: S3B_NEXT_FIXED_LOR,
    S3B_CONDITIONAL_UNSTABLE: S3B_NEXT_FIXED_LOR,
    S3B_CONDITIONAL_NOT_QUALIFIED: S3B_NEXT_FIXED_LOR,
    S3B_FIVE_SOURCE_PASS: S3B_NEXT_FACTOR_FREE_PRODUCTIONIZATION,
    S3B_FIVE_SOURCE_NO_SIGNAL: S3B_NEXT_FIXED_LOR,
    S3B_FIVE_SOURCE_UNSTABLE: S3B_NEXT_FIXED_LOR,
}
THREAD_ENV = {
    "OMP_NUM_THREADS": str(TASK040_LEVEL_A_THREADS),
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "PYTHONUNBUFFERED": "1",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _worker_command(plan: dict[str, Any]) -> list[str]:
    run_directory = Path(plan["run_directory"])
    worker_directory = Path(plan["worker_run_directory"])
    command = [
        "mpiexec",
        "-n",
        str(TASK040_LEVEL_A_MPI_SIZE),
        sys.executable,
        "-m",
        "benchmarks.task040_level_a",
        "--input",
        plan["input"],
        "--exact-spool-root",
        plan["exact_spool_root"],
        "--run-directory",
        str(worker_directory),
        "--source-sha",
        plan["source_sha"],
        "--memory-stages",
        str(run_directory / "memory_stages.jsonl"),
        "--memory-markers",
        str(run_directory / "memory_stage_markers.raw.jsonl"),
    ]
    if plan.get("scalar_krylov") is True:
        command.append(TASK040_V1_1_SCALAR_KRYLOV_FLAG)
    if plan.get("interface_schur") is True:
        command.append(TASK040_V1_2_INTERFACE_SCHUR_FLAG)
    if plan.get("packet_producer") is True:
        command.append(TASK040_V2_INTERFACE_PACKET_PRODUCER_FLAG)
    if plan.get("v4_exact_authority_compatibility") is True:
        command.append(TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_FLAG)
    if plan.get("v5_fresh_bare_f_authority") is True:
        command.append(TASK040_V5_FRESH_BARE_F_AUTHORITY_FLAG)
        command.extend(("--watchdog-enabled", "--bottom-route-only"))
    if plan.get("v5_route_c") is True:
        command.append(TASK040_V5_ROUTE_C_FLAG)
        command.extend(("--watchdog-enabled", "--bottom-route-only"))
    if plan.get("v9_e_lor_l2_only") is True:
        command.append(V9_E_LOR_L2_ONLY_FLAG)
    elif plan.get("v9_c0_explicit_coarse_only") is True:
        command.append(V9_C0_EXPLICIT_COARSE_ONLY_FLAG)
    elif plan.get("v8_adaptive_stage_bc_only") is True:
        command.append(V8_ADAPTIVE_STAGE_BC_ONLY_FLAG)
    elif plan.get("v9_source_bridge_only") is True:
        command.append(V9_SOURCE_BRIDGE_ONLY_FLAG)
    elif plan.get("v9_e_s3_j1_baseline_only") is True:
        command.append(V9_E_S3_J1_BASELINE_ONLY_FLAG)
    elif plan.get("v9_e_s3_structured_b1_only") is True:
        command.append(V9_E_S3_STRUCTURED_B1_ONLY_FLAG)
        baseline_manifest = plan["baseline_manifest"]
        command.extend(
            (
                V9_E_S3_J1_BASELINE_MANIFEST_OPTION,
                str(baseline_manifest["path"]),
                V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION,
                str(baseline_manifest["sha256"]),
            )
        )
    elif plan.get("v8_adaptive_stage_b1_only") is True:
        command.append(V8_ADAPTIVE_STAGE_B1_ONLY_FLAG)
    elif plan.get("v8_adaptive_schwarz_only") is True:
        command.append(V8_ADAPTIVE_SCHWARZ_ONLY_FLAG)
    elif plan.get("v8_full_spectrum_only") is True:
        command.append(V8_FULL_SPECTRUM_ONLY_FLAG)
        if plan.get("v9_source_packet_root") is not None:
            command.extend(
                (
                    V9_SOURCE_PACKET_ROOT_OPTION,
                    str(plan["v9_source_packet_root"]),
                    V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION,
                    str(plan["v9_source_packet_manifest_sha256"]),
                )
            )
    elif plan.get("v7_moving_pml_full_state") is True:
        command.append(V7_MOVING_PML_FULL_STATE_FLAG)
    elif plan.get("v7_scale_normalized_identity") is True:
        command.append(V7_SCALE_NORMALIZED_IDENTITY_FLAG)
    elif plan.get("v6_2_interface_schur") is True:
        command.append(TASK040_V6_2_INTERFACE_SCHUR_FLAG)
    if (
        plan.get("v8_adaptive_stage_bc_only") is True
        or plan.get("v9_source_bridge_only") is True
        or plan.get("v9_c0_explicit_coarse_only") is True
        or plan.get("v9_e_lor_l2_only") is True
        or plan.get("v8_adaptive_stage_b1_only") is True
        or plan.get("v8_adaptive_schwarz_only") is True
        or plan.get("v8_full_spectrum_only") is True
        or plan.get("v7_moving_pml_full_state") is True
        or plan.get("v7_scale_normalized_identity") is True
        or plan.get("v6_2_interface_schur") is True
        or plan.get("v9_e_s3_j1_baseline_only") is True
        or plan.get("v9_e_s3_structured_b1_only") is True
    ):
        command.extend(
            (
                "--watchdog-hard-stop-bytes",
                str(plan["watchdog"]["hard_stop_bytes"]),
                "--watchdog-enabled",
                "--bottom-route-only",
            )
        )
    if plan.get("coupled_interface") is True:
        command.extend(
            [
                TASK040_V3_2_COUPLED_INTERFACE_FLAG,
                "--interface-packet-root",
                str(plan["interface_packet_root"]),
            ]
        )
    elif plan.get("packet_consumer") is True:
        command.extend(
            [
                TASK040_V2_INTERFACE_PACKET_CONSUMER_FLAG,
                "--interface-packet-root",
                str(plan["interface_packet_root"]),
            ]
        )
    return command


def build_task040_level_a_watchdog_plan(
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
    v9_e_s3_j1_baseline_only: bool = False,
    v9_e_s3_structured_b1_only: bool = False,
    v9_e_s3_j1_baseline_manifest: str | Path | None = None,
    v9_e_s3_j1_baseline_manifest_sha256: str | None = None,
    v9_source_packet_root: str | Path | None = None,
    v9_source_packet_manifest_sha256: str | None = None,
    interface_packet_root: str | Path | None = None,
) -> dict[str, Any]:
    s3_route_requested = bool(
        v9_e_s3_j1_baseline_only or v9_e_s3_structured_b1_only
    )
    if s3_route_requested and Path(run_directory).resolve() == Path(
        exact_spool_root
    ).resolve():
        raise ValueError(
            "S3b requires an outer run_directory distinct from exact_spool_root"
        )
    plan = build_task040_level_a_plan(
        input_path=input_path,
        exact_spool_root=exact_spool_root,
        run_directory=run_directory,
        source_sha=source_sha,
        scalar_krylov=scalar_krylov,
        interface_schur=interface_schur,
        packet_producer=packet_producer,
        packet_consumer=packet_consumer,
        coupled_interface=coupled_interface,
        v4_exact_authority_compatibility=v4_exact_authority_compatibility,
        v5_fresh_bare_f_authority=v5_fresh_bare_f_authority,
        v5_route_c=v5_route_c,
        v6_2_interface_schur=v6_2_interface_schur,
        v7_scale_normalized_identity=v7_scale_normalized_identity,
        v7_moving_pml_full_state=v7_moving_pml_full_state,
        v8_full_spectrum_only=v8_full_spectrum_only,
        v8_adaptive_schwarz_only=v8_adaptive_schwarz_only,
        v8_adaptive_stage_b1_only=v8_adaptive_stage_b1_only,
        v8_adaptive_stage_bc_only=v8_adaptive_stage_bc_only,
        v9_source_bridge_only=v9_source_bridge_only,
        v9_c0_explicit_coarse_only=v9_c0_explicit_coarse_only,
        v9_e_lor_l2_only=v9_e_lor_l2_only,
        v9_e_s3_j1_baseline_only=v9_e_s3_j1_baseline_only,
        v9_e_s3_structured_b1_only=v9_e_s3_structured_b1_only,
        v9_e_s3_j1_baseline_manifest=v9_e_s3_j1_baseline_manifest,
        v9_e_s3_j1_baseline_manifest_sha256=(
            v9_e_s3_j1_baseline_manifest_sha256
        ),
        v9_source_packet_root=v9_source_packet_root,
        v9_source_packet_manifest_sha256=v9_source_packet_manifest_sha256,
        interface_packet_root=interface_packet_root,
    )
    worker_directory = Path(plan["run_directory"]) / "worker"
    if packet_producer:
        plan["packet_root"] = str(worker_directory / "interface_packet")
    plan["watchdog"] = {
        "sample_interval_seconds": SAMPLE_INTERVAL_SECONDS,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "absolute_terminate_memory_bytes": plan["absolute_terminate_memory_bytes"],
        "swap_limit_bytes": SWAP_LIMIT_BYTES,
        "process_group": True,
        "terminate_entire_process_group": True,
        "resource_authority": "task034_wsl_resources.resource_authority_sample",
    }
    if v5_fresh_bare_f_authority:
        plan["watchdog"].update(
            {
                "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                "warning_memory_bytes": int(plan["warning_memory_bytes"]),
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
            }
        )
    elif packet_producer:
        plan["watchdog"]["preferred_memory_bytes"] = int(plan["preferred_memory_bytes"])
    elif v5_route_c:
        plan["watchdog"].update(
            {
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "timeout_seconds": int(plan["timeout_seconds"]),
                "route_c_resource_policy": "45_gib_hard_line_swap0",
                "bottom_route_only": True,
                "process_tree_watchdog_enabled": True,
            }
        )
    elif v9_e_s3_j1_baseline_only or v9_e_s3_structured_b1_only:
        baseline = bool(v9_e_s3_j1_baseline_only)
        plan["watchdog"].update(
            {
                "v9_e_s3_j1_baseline_only": baseline,
                "v9_e_s3_structured_b1_only": not baseline,
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "swap_limit_bytes": SWAP_LIMIT_BYTES,
                "timeout_seconds": int(plan["timeout_seconds"]),
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
                "source_order": list(plan["source_order"]),
                "planned_source_order": list(plan["planned_source_order"]),
                "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                "conditional_checkpoints": list(plan["conditional_checkpoints"]),
                "cleanup_stage": (
                    "s3b_j1_cleanup_complete"
                    if baseline
                    else "s3b_b1_cleanup_complete"
                ),
                "marker_sequence": list(
                    V9_E_S3_MARKER_SEQUENCE
                    if baseline
                    else V9_E_S3_B1_MARKER_SEQUENCE
                ),
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
                "stage_timeout_seconds": None,
            }
        )
        if not baseline:
            plan["watchdog"]["baseline_manifest"] = dict(
                plan["baseline_manifest"]
            )
    elif (
        v9_source_bridge_only
        or v9_c0_explicit_coarse_only
        or v9_e_lor_l2_only
        or v8_adaptive_stage_bc_only
        or v8_adaptive_stage_b1_only
        or v8_adaptive_schwarz_only
        or v8_full_spectrum_only
        or v7_moving_pml_full_state
        or v7_scale_normalized_identity
        or v6_2_interface_schur
    ):
        plan["watchdog"].update(
            {
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "swap_limit_bytes": 0,
                "timeout_seconds": int(plan["timeout_seconds"]),
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
                "numeric_allgather": False,
                "full_interface_replica_per_rank": False,
            }
        )
        if v9_e_lor_l2_only:
            plan["watchdog"].update(
                {
                    "v9_e_lor_l2_only": True,
                    "hard_stop_bytes": V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "timeout_seconds": V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
                    "process_tree_watchdog_enabled": True,
                    "bottom_route_only": True,
                    "cleanup_stage": "v9_e_lor_l2_cleanup_complete",
                    "marker_sequence": list(V9_E_LOR_L2_MARKER_SEQUENCE),
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                    "stage_timeout_seconds": None,
                    "global_lor_matrix": "not_materialized",
                }
            )
        elif v9_c0_explicit_coarse_only:
            plan["watchdog"].update(
                {
                    "v9_c0_explicit_coarse_only": True,
                    "minimum_mem_available_bytes": V9_C0_MIN_AVAILABLE_BYTES,
                    "preferred_memory_bytes": V9_C0_PREFERRED_MEMORY_BYTES,
                    "warning_memory_bytes": V9_C0_WARNING_MEMORY_BYTES,
                    "hard_stop_bytes": V9_C0_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "timeout_seconds": V9_C0_TIMEOUT_SECONDS,
                    "setup_target_seconds": V9_C0_SETUP_TARGET_SECONDS,
                    "one_apply_target_seconds": V9_C0_ONE_APPLY_TARGET_SECONDS,
                    "source_order": list(plan["source_order"]),
                    "planned_source_order": list(plan["planned_source_order"]),
                    "mandatory_checkpoints": [],
                    "conditional_checkpoints": [8],
                    "cleanup_stage": "v9_c0_cleanup_complete",
                    "marker_sequence": list(V9_C0_MARKER_SEQUENCE),
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                    "source_only": True,
                    "coarse_cardinality": "630_patches_x_160_columns",
                }
            )
        elif v9_source_bridge_only:
            plan["watchdog"].update(
                {
                    "v9_source_bridge_only": True,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "source_order": list(plan["source_order"]),
                    "planned_source_order": list(plan["planned_source_order"]),
                    "mandatory_checkpoints": [],
                    "conditional_checkpoints": [],
                    "cleanup_stage": "v9_source_bridge_cleanup_complete",
                    "source_only": True,
                    "setup_target_seconds": None,
                    "one_apply_target_seconds": None,
                    "numeric_allgather": False,
                    "full_numeric_replica": False,
                }
            )
        elif v8_adaptive_stage_bc_only:
            plan["watchdog"].update(
                {
                    "v8_adaptive_stage_bc_only": True,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "source_order": list(plan["source_order"]),
                    "planned_source_order": list(plan["planned_source_order"]),
                    "mandatory_checkpoints": [16, 32, 64],
                    "conditional_checkpoints": [],
                    "cleanup_stage": "v8_adaptive_stage_bc_cleanup_complete",
                    "symbolic_only": False,
                    "stage_bc_only": True,
                }
            )
        elif v8_adaptive_stage_b1_only:
            plan["watchdog"].update(
                {
                    "v8_adaptive_stage_b1_only": True,
                    "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                    "one_apply_target_seconds": None,
                    "source_order": [],
                    "mandatory_checkpoints": [],
                    "conditional_checkpoints": [],
                    "cleanup_stage": (
                        "v8_adaptive_stage_b1_cleanup_complete"
                    ),
                    "symbolic_only": True,
                }
            )
        elif v8_adaptive_schwarz_only:
            plan["watchdog"].update(
                {
                    "v8_adaptive_schwarz_only": True,
                    "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "timeout_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "setup_target_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                    "one_apply_target_seconds": (
                        V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS
                    ),
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "conditional_checkpoints": [],
                    "cleanup_stage": "v8_adaptive_cleanup_complete",
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
        elif v8_full_spectrum_only:
            plan["watchdog"].update(
                {
                    "v8_full_spectrum_only": True,
                    "minimum_mem_available_bytes": int(
                        plan["minimum_mem_available_bytes"]
                    ),
                    "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                    "setup_target_seconds": V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS,
                    "transform_target_seconds": V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS,
                    "one_apply_target_seconds": V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS,
                    "timeout_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "conditional_checkpoints": list(plan["conditional_checkpoints"]),
                    "metadata_only_descriptor_gather": True,
                    "root_metadata_gather": True,
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
            if plan.get("v9_source_packet_root") is not None:
                plan["watchdog"].update(
                    {
                        "v9_corrected_source_packet": True,
                        "v9_source_packet_root": plan[
                            "v9_source_packet_root"
                        ],
                        "v9_source_packet_manifest_sha256": plan[
                            "v9_source_packet_manifest_sha256"
                        ],
                        "v9_marker_stages": [
                            "v9_full_spectrum_source_packet_validated",
                            "v9_full_spectrum_external_owner_vector_ready",
                            "v9_full_spectrum_random0_owner_vector_ready",
                        ],
                        "setup_target_seconds": 1800,
                        "transform_target_seconds": 900,
                        "one_apply_target_seconds": 1200,
                        "timeout_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                        "minimum_mem_available_bytes": 96 * 2**30,
                        "corrected_packet_source": True,
                    }
                )
        elif v7_moving_pml_full_state:
            plan["watchdog"].update(
                {
                    "v7_moving_pml_full_state": True,
                    "source_order": list(plan["source_order"]),
                    "mandatory_checkpoints": list(plan["mandatory_checkpoints"]),
                    "fixed_configuration": dict(plan["fixed_configuration"]),
                    "pml_profile": "quadratic",
                    "integrated_attenuation": 6.0,
                    "numeric_allgather": False,
                    "full_interface_replica_per_rank": False,
                }
            )
        elif v7_scale_normalized_identity:
            plan["watchdog"].update(
                {
                    "v7_identity_preferred_memory_bytes": int(
                        plan["preferred_memory_bytes"]
                    ),
                    "v7_identity_target_seconds": int(
                        plan["identity_target_seconds"]
                    ),
                    "v7_identity_hard_seconds": int(
                        plan["identity_hard_seconds"]
                    ),
                    "v7_scale_normalized_identity": True,
                    "root_metadata_gather": bool(plan["root_metadata_gather"]),
                    "metadata_only_descriptor_gather": bool(
                        plan["metadata_only_descriptor_gather"]
                    ),
                }
            )
        else:
            plan["watchdog"].update(
                {
                    "minimum_mem_available_bytes": int(
                        plan["minimum_mem_available_bytes"]
                    ),
                    "minimum_disk_free_bytes": int(
                        plan["minimum_disk_free_bytes"]
                    ),
                    "v6_2_identity_only": False,
                    "v6_2_exact_qualification": True,
                    "same_process_exact_lifecycle": True,
                    "root_metadata_gather": True,
                    "support_metadata_replicated": True,
                }
            )
    plan["worker_run_directory"] = str(worker_directory)
    plan["worker_argv"] = _worker_command(plan)
    plan["runner_reuse"] = {
        "task040_worker": "benchmarks/task040_level_a.py",
        "process_control": "benchmarks.watchdog_process_control",
        "system_and_source": "Task039 h4 bottom APIs",
    }
    return plan


def _latest_stage(path: Path) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "process_start", "waiting_for_progress"
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return str(payload.get("stage", "unknown")), str(
            payload.get("status", "unknown")
        )
    return "process_start", "waiting_for_progress"


def _v9_c0_prelaunch_resource_preflight() -> dict[str, Any]:
    memory = wsl_memory_snapshot()
    values: dict[str, int | None] = {"SwapTotal": None, "SwapFree": None}
    error = None
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        lines = []
        error = f"{type(exc).__name__}: {exc}"
    for line in lines:
        fields = line.split()
        if len(fields) >= 2 and fields[0].rstrip(":") in values:
            try:
                values[fields[0].rstrip(":")] = int(fields[1]) * 1024
            except ValueError:
                error = f"invalid /proc/meminfo value for {fields[0]}"
    swap_total = values["SwapTotal"]
    swap_free = values["SwapFree"]
    swap_used = (
        None
        if not isinstance(swap_total, int)
        or not isinstance(swap_free, int)
        or swap_free > swap_total
        else swap_total - swap_free
    )
    checks = {
        "mem_available_at_least_320_gib": (
            isinstance(memory.get("mem_available_bytes"), int)
            and int(memory["mem_available_bytes"]) >= V9_C0_MIN_AVAILABLE_BYTES
        ),
        "host_used_swap_zero": swap_used == 0,
        "meminfo_readable": error is None,
    }
    return {
        "authority": "host_proc_meminfo",
        "mem_available_bytes": memory.get("mem_available_bytes"),
        "mem_total_bytes": memory.get("mem_total_bytes"),
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "swap_used_bytes": swap_used,
        "minimum_mem_available_bytes": V9_C0_MIN_AVAILABLE_BYTES,
        "swap_semantics": "SwapTotal-SwapFree",
        "checks": checks,
        "pass": bool(all(checks.values())),
        "error": error,
    }


_V9_C0_POST_SETUP_STAGES = frozenset(
    {
        "v9_c0_coarse_ready",
        "v9_c0_pre_one_apply_resource",
        "v9_c0_external_one_apply_begin",
        "v9_c0_external_one_apply_end",
        "v9_c0_outer_checkpoint",
        "v9_c0_classification",
        "v9_c0_cleanup_complete",
    }
)


def _v9_c0_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    total = float(total_elapsed_seconds)
    if total >= V9_C0_TIMEOUT_SECONDS:
        limit = float(V9_C0_TIMEOUT_SECONDS)
        elapsed = total
        kind = "total"
    elif stage == "v9_c0_external_one_apply_begin":
        limit = float(V9_C0_ONE_APPLY_TARGET_SECONDS)
        elapsed = float(stage_elapsed_seconds)
        kind = "one_apply"
    elif stage in _V9_C0_POST_SETUP_STAGES:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "elapsed_seconds": float(stage_elapsed_seconds),
            "classification": None,
        }
    else:
        limit = float(V9_C0_SETUP_TARGET_SECONDS)
        elapsed = total
        kind = "setup"
    timed_out = elapsed >= limit
    return {
        "active": True,
        "timed_out": timed_out,
        "kind": kind,
        "limit_seconds": limit,
        "elapsed_seconds": elapsed,
        "classification": (
            V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION if timed_out else None
        ),
    }


def _v9_e_lor_l2_active_stage_timeout(
    stage: str,
    stage_elapsed: float,
    total_elapsed: float,
) -> dict[str, Any]:
    """Apply only the fixed total wall cap to the L2 action-only route."""

    del stage, stage_elapsed
    elapsed = float(total_elapsed)
    return {
        "kind": "total",
        "stage_target_seconds": None,
        "total_target_seconds": V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
        "stage_elapsed_seconds": None,
        "total_elapsed_seconds": elapsed,
        "timed_out": elapsed >= V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
    }


def _v8_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Apply only the V8 active-stage limits and the total wall limit."""

    if float(total_elapsed_seconds) >= V8_FULL_SPECTRUM_TIMEOUT_SECONDS:
        return {
            "active": True,
            "timed_out": True,
            "kind": "total",
            "limit_seconds": float(V8_FULL_SPECTRUM_TIMEOUT_SECONDS),
            "classification": V8_RESOURCE_UNAVAILABLE_CLASSIFICATION,
        }
    if stage.endswith("_one_apply_begin"):
        limit = float(V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS)
        kind = "one_apply"
    elif stage == "v8_full_spectrum_group2_factor_ready":
        limit = 2.0 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
        kind = "transform_or_symbol"
    elif (
        stage == "process_start"
        or stage == "v8_full_spectrum_preflight"
        or stage == "v8_full_spectrum_system_ready"
        or "_factor_ready" in stage
    ):
        limit = 2.0 * V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS
        kind = "setup_or_factor"
    elif "transform_ready" in stage or stage.endswith("_symbol_ready"):
        limit = 2.0 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
        kind = "transform_or_symbol"
    else:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "classification": None,
        }
    elapsed = float(stage_elapsed_seconds)
    return {
        "active": True,
        "timed_out": elapsed > limit,
        "kind": kind,
        "limit_seconds": limit,
        "classification": (
            V8_RESOURCE_UNAVAILABLE_CLASSIFICATION if elapsed > limit else None
        ),
    }


def _v9_full_spectrum_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Apply the corrected packet route's unscaled stage limits."""

    if float(total_elapsed_seconds) >= V8_FULL_SPECTRUM_TIMEOUT_SECONDS:
        limit, kind = V8_FULL_SPECTRUM_TIMEOUT_SECONDS, "total"
        elapsed = float(total_elapsed_seconds)
    elif stage.endswith("_one_apply_begin"):
        limit, kind = V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS, "one_apply"
        elapsed = float(stage_elapsed_seconds)
    elif stage == "v8_full_spectrum_group2_factor_ready" or stage.endswith(
        "_transform_ready"
    ):
        limit, kind = V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS, "transform_or_symbol"
        elapsed = float(stage_elapsed_seconds)
    elif stage.endswith("_symbol_ready") or stage in {
        "process_start",
        "v8_full_spectrum_preflight",
        "v8_full_spectrum_system_ready",
        "v8_full_spectrum_group0_factor_ready",
        "v8_full_spectrum_group1_factor_ready",
        "v9_full_spectrum_source_packet_validated",
        "v9_full_spectrum_external_owner_vector_ready",
        "v9_full_spectrum_random0_owner_vector_ready",
    }:
        limit, kind = V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS, "setup_or_factor"
        elapsed = float(stage_elapsed_seconds)
    else:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "classification": None,
        }
    timed_out = elapsed > float(limit)
    return {
        "active": True,
        "timed_out": timed_out,
        "kind": kind,
        "limit_seconds": float(limit),
        "classification": (
            V8_RESOURCE_UNAVAILABLE_CLASSIFICATION if timed_out else None
        ),
    }


def _v8_adaptive_active_stage_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Return the fixed Stage-A marker timeout without changing old V8."""

    if float(total_elapsed_seconds) >= V8_ADAPTIVE_TIMEOUT_SECONDS:
        limit = float(V8_ADAPTIVE_TIMEOUT_SECONDS)
        kind = "total"
    elif stage.endswith("_one_apply_begin"):
        limit = float(V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS)
        kind = "one_apply"
    elif stage in {
        "process_start",
        "v8_adaptive_preflight",
        "v8_adaptive_system_ready",
        "v8_adaptive_factor_ready",
        "v8_adaptive_stage_b1_preflight",
        "v8_adaptive_stage_b1_system_ready",
        "v8_adaptive_stage_b1_factor_ready",
    }:
        limit = float(V8_ADAPTIVE_SETUP_TARGET_SECONDS)
        kind = "setup_or_factor"
    else:
        return {
            "active": False,
            "timed_out": False,
            "kind": None,
            "limit_seconds": None,
            "classification": None,
        }
    elapsed = float(
        total_elapsed_seconds if kind == "total" else stage_elapsed_seconds
    )
    return {
        "active": True,
        "timed_out": elapsed > limit,
        "kind": kind,
        "limit_seconds": limit,
        "classification": (
            V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION
            if elapsed > limit
            else None
        ),
    }


def _v8_adaptive_stage_bc_total_timeout(
    stage: str,
    stage_elapsed_seconds: float,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    """Apply only Stage-B/C's 10800-second total wall limit."""

    limit = float(V8_ADAPTIVE_TIMEOUT_SECONDS)
    return {
        "active": True,
        "timed_out": float(total_elapsed_seconds) >= limit,
        "kind": "total",
        "limit_seconds": limit,
        "stage": stage,
        "stage_elapsed_seconds": float(stage_elapsed_seconds),
        "total_elapsed_seconds": float(total_elapsed_seconds),
        "classification": (
            "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
            if float(total_elapsed_seconds) >= limit
            else None
        ),
    }


def _v8_adaptive_swap_authority_sample(
    authority: dict[str, Any], *, terminal_excluded: bool
) -> dict[str, Any]:
    """Evaluate one adaptive swap sample, including the scoped zero fallback."""

    if terminal_excluded:
        return {
            "counted": False,
            "authority_readable": True,
            "swap_zero": True,
            "fallback_used": False,
            "semantics": "terminal_teardown_excluded",
        }
    process_tree = authority.get("process_tree", {})
    cgroup = authority.get("job_cgroup", {})
    process_complete = bool(process_tree.get("all_status_readable"))
    process_swap = process_tree.get("swap_bytes")
    dedicated = bool(cgroup.get("dedicated_job_cgroup"))
    cgroup_readable = bool(cgroup.get("readable"))
    cgroup_swap = cgroup.get("swap_current_bytes")
    if process_complete:
        cgroup_ok = (
            not dedicated
            or (cgroup_readable and cgroup_swap == SWAP_LIMIT_BYTES)
        )
        readable = process_swap == SWAP_LIMIT_BYTES and cgroup_ok
        return {
            "counted": True,
            "authority_readable": readable,
            "swap_zero": readable,
            "fallback_used": False,
            "semantics": (
                "complete_process_tree_vm_swap"
                if readable
                else "complete_process_tree_or_dedicated_cgroup_invalid"
            ),
        }
    fallback = (
        not dedicated
        and cgroup_readable
        and cgroup_swap == SWAP_LIMIT_BYTES
    )
    return {
        "counted": True,
        "authority_readable": fallback,
        "swap_zero": fallback,
        "fallback_used": fallback,
        "semantics": (
            "nonterminal_incomplete_process_tree_non_dedicated_cgroup_zero_upper_bound"
            if fallback
            else "incomplete_process_tree_swap_authority_unavailable"
        ),
    }


def _terminal_teardown_sample_excluded(
    *,
    post_sample_return_code: int | None,
    process_tree: dict[str, Any],
    run_summary_path: Path,
    latest_stage: str,
    latest_stage_status: str,
) -> bool:
    """Recognize only the post-cleanup ``/proc`` teardown race.

    A worker that is still live, or whose run summary/terminal cleanup stage is
    not complete, remains an authoritative telemetry failure when its process
    tree is unreadable.  The caller performs RSS and swap limits independently
    before accepting this exclusion.
    """
    return bool(
        post_sample_return_code is None
        and run_summary_path.is_file()
        and latest_stage in _TERMINAL_CLEANUP_STAGES
        and latest_stage_status == "complete"
        and process_tree.get("pids")
        and process_tree.get("all_status_readable") is False
    )


def _terminal_teardown_termination_reason(
    *,
    rss_bytes: int,
    swap_bytes: int,
    dedicated_swap_bytes: int | None,
    hard_stop_bytes: int,
) -> str:
    """Apply resource limits before accepting a natural teardown exit."""
    if rss_bytes >= hard_stop_bytes:
        return "absolute_memory_limit"
    if swap_bytes > SWAP_LIMIT_BYTES or (
        dedicated_swap_bytes is not None
        and dedicated_swap_bytes > SWAP_LIMIT_BYTES
    ):
        return "swap_detected"
    return "natural_exit"


def _s3_completion_gate(
    *,
    route_kind: str,
    termination_reason: str,
    return_code: int | None,
    elapsed_seconds: float,
    summary_present: bool,
    latest_stage: str,
    latest_stage_status: str,
    resource_gate: bool,
    worker_payload: Mapping[str, Any] | None,
    resource_limits: Mapping[str, Any],
    expected_manifest_path: str | Path | None = None,
    expected_manifest_sha256: str | None = None,
    expected_input_path: str | Path | None = None,
    expected_input_sha256: str | None = None,
    expected_source_sha: str | None = None,
) -> dict[str, Any]:
    """Adjudicate only the process/manifest completion contract for S3b."""

    if route_kind == "baseline":
        expected_schema = V9_E_S3_J1_BASELINE_SCHEMA
        expected_cleanup_stage = "s3b_j1_cleanup_complete"
    elif route_kind == "candidate":
        expected_schema = V9_E_S3_B1_SCHEMA
        expected_cleanup_stage = "s3b_b1_cleanup_complete"
    else:
        raise ValueError(f"unknown S3 route kind: {route_kind}")

    payload = worker_payload if isinstance(worker_payload, Mapping) else {}
    try:
        elapsed = float(elapsed_seconds)
        wall_limit = float(resource_limits["total_wall_seconds"])
    except (KeyError, TypeError, ValueError, OverflowError):
        elapsed = float("nan")
        wall_limit = float("nan")
    wall_time_gate = (
        elapsed >= 0.0 and wall_limit >= 0.0 and elapsed < wall_limit
    )
    classification = payload.get("classification")
    next_stage = payload.get("next_stage")
    payload_error = payload.get("error")
    provenance = payload.get("provenance")
    common_checks = {
        "natural_exit": termination_reason == "natural_exit",
        "return_code_zero": return_code == 0,
        "total_wall_gate": wall_time_gate,
        "summary_present": bool(summary_present),
        "expected_cleanup_stage": (
            latest_stage == expected_cleanup_stage
            and latest_stage_status == "complete"
        ),
        "schema": payload.get("schema") == expected_schema,
        "route": payload.get("route") == "V9_E_S3B",
        "resource_gate": bool(resource_gate),
        "payload_error_none": "error" in payload and payload_error is None,
        "input_path_binding": (
            isinstance(provenance, Mapping)
            and expected_input_path is not None
            and provenance.get("input_path") == str(expected_input_path)
        ),
        "input_sha256_binding": (
            isinstance(provenance, Mapping)
            and isinstance(expected_input_sha256, str)
            and provenance.get("input_sha256") == expected_input_sha256
        ),
        "source_sha_binding": (
            isinstance(provenance, Mapping)
            and isinstance(expected_source_sha, str)
            and provenance.get("source_sha") == expected_source_sha
        ),
    }
    common_complete = bool(all(common_checks.values()))

    if route_kind == "baseline":
        route_checks = {
            "baseline_only": payload.get("baseline_only") is True,
            "measured_classification": (
                classification == "S3B_J1_BASELINE_MEASURED"
            ),
        }
        baseline_manifest_usable = bool(
            common_complete and all(route_checks.values())
        )
        candidate_outcome_ready = False
    else:
        binding = payload.get("baseline_manifest_binding")
        binding_path = (
            binding.get("path") if isinstance(binding, Mapping) else None
        )
        expected_sha = (
            binding.get("expected_sha256")
            if isinstance(binding, Mapping)
            else None
        )
        observed_sha = (
            binding.get("observed_sha256")
            if isinstance(binding, Mapping)
            else None
        )
        expected_sha_valid = (
            isinstance(expected_sha, str)
            and len(expected_sha) == 64
            and all(
                character in "0123456789abcdef" for character in expected_sha
            )
        )
        observed_sha_valid = (
            isinstance(observed_sha, str)
            and len(observed_sha) == 64
            and all(
                character in "0123456789abcdef" for character in observed_sha
            )
        )
        expected_plan_sha_valid = (
            isinstance(expected_manifest_sha256, str)
            and len(expected_manifest_sha256) == 64
            and all(
                character in "0123456789abcdef"
                for character in expected_manifest_sha256
            )
        )
        route_checks = {
            "validated_baseline": (
                isinstance(payload.get("validated_baseline"), Mapping)
                and payload["validated_baseline"].get("validated") is True
            ),
            "baseline_manifest_sha_binding": (
                isinstance(payload.get("validated_baseline"), Mapping)
                and payload["validated_baseline"].get("manifest_sha256")
                == expected_manifest_sha256
            ),
            "baseline_binding_sha": (
                expected_plan_sha_valid
                and expected_sha_valid
                and observed_sha_valid
                and expected_sha == expected_manifest_sha256
                and observed_sha == expected_manifest_sha256
            ),
            "baseline_binding_path": (
                isinstance(binding_path, str)
                and expected_manifest_path is not None
                and binding_path == str(expected_manifest_path)
            ),
            "classification": (
                classification in _S3_CANDIDATE_TERMINAL_NEXT_STAGES
            ),
            "next_stage": (
                classification in _S3_CANDIDATE_TERMINAL_NEXT_STAGES
                and next_stage
                == _S3_CANDIDATE_TERMINAL_NEXT_STAGES.get(classification)
            ),
        }
        baseline_manifest_usable = False
        candidate_outcome_ready = bool(
            common_complete and all(route_checks.values())
        )

    return {
        "route_kind": route_kind,
        "workflow_completed": bool(
            baseline_manifest_usable or candidate_outcome_ready
        ),
        "baseline_manifest_usable": baseline_manifest_usable,
        "candidate_outcome_ready": candidate_outcome_ready,
        "worker_schema": payload.get("schema"),
        "worker_classification": classification,
        "worker_next_stage": next_stage,
        "worker_error": payload_error,
        "latest_stage": latest_stage,
        "latest_stage_status": latest_stage_status,
        "elapsed_seconds": elapsed,
        "wall_time_gate": wall_time_gate,
        "resource_gate": bool(resource_gate),
        "resource_limits": dict(resource_limits),
        "common_checks": common_checks,
        "route_checks": route_checks,
    }


def _write_jsonl(stream: Any, payload: dict[str, Any]) -> None:
    stream.write(json.dumps(payload, sort_keys=True) + "\n")
    stream.flush()


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(THREAD_ENV)
    return environment


def run_task040_level_a_watchdog(plan: dict[str, Any]) -> int:
    run_directory = Path(plan["run_directory"])
    if run_directory.exists():
        raise FileExistsError(f"Task040 run directory already exists: {run_directory}")
    run_directory.mkdir(parents=True, exist_ok=False)
    stages_path = run_directory / "memory_stages.jsonl"
    markers_path = run_directory / "memory_stage_markers.raw.jsonl"
    timeline_path = run_directory / "process_tree_samples.jsonl"
    stdout_path = run_directory / "worker_stdout.txt"
    summary_path = run_directory / "watchdog_summary.json"
    worker_directory = Path(plan["worker_run_directory"])
    run_summary = worker_directory / "run_summary.json"
    if worker_directory.exists():
        raise FileExistsError(
            f"Task040 worker output directory already exists: {worker_directory}"
        )
    command = list(plan["worker_argv"])
    hard_stop_bytes = int(plan["absolute_terminate_memory_bytes"])
    c0_enabled = bool(plan.get("v9_c0_explicit_coarse_only"))
    s3_j1_enabled = bool(plan.get("v9_e_s3_j1_baseline_only"))
    s3_b1_enabled = bool(plan.get("v9_e_s3_structured_b1_only"))
    s3_enabled = s3_j1_enabled or s3_b1_enabled
    l2_enabled = bool(plan.get("v9_e_lor_l2_only"))
    stage_a_enabled = bool(plan.get("v8_adaptive_schwarz_only"))
    b1_enabled = bool(plan.get("v8_adaptive_stage_b1_only"))
    stage_bc_enabled = bool(plan.get("v8_adaptive_stage_bc_only"))
    v9_enabled = bool(plan.get("v9_source_bridge_only"))
    v9_corrected_full_enabled = bool(
        plan.get("v9_corrected_source_packet")
    )
    timeout_seconds = int(
        V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS
        if l2_enabled
        else V9_C0_TIMEOUT_SECONDS
        if c0_enabled
        else V8_ADAPTIVE_TIMEOUT_SECONDS
        if stage_bc_enabled or v9_enabled
        else plan.get("timeout_seconds", TASK040_LEVEL_A_TIMEOUT_SECONDS)
    )
    adaptive_enabled = stage_a_enabled or b1_enabled
    v8_enabled = (
        bool(plan.get("v8_full_spectrum_only"))
        or adaptive_enabled
        or stage_bc_enabled
        or v9_enabled
        or c0_enabled
        or l2_enabled
    )
    active_timeout = (
        _v9_e_lor_l2_active_stage_timeout
        if l2_enabled
        else _v9_c0_active_stage_timeout
        if c0_enabled
        else _v8_adaptive_stage_bc_total_timeout
        if stage_bc_enabled or v9_enabled
        else _v9_full_spectrum_active_stage_timeout
        if v9_corrected_full_enabled
        else _v8_adaptive_active_stage_timeout
        if adaptive_enabled
        else _v8_active_stage_timeout
    )
    last_stage = "process_start"
    last_stage_status = "waiting_for_progress"
    stage_started = time.monotonic()
    started = time.monotonic()
    sample_count = 0
    terminal_teardown_excluded_count = 0
    peak_rss_bytes = 0
    peak_swap_bytes = 0
    all_status_readable = True
    dedicated_cgroup_present = False
    dedicated_cgroup_swap_readable = True
    peak_dedicated_cgroup_swap_bytes = 0
    adaptive_swap_authority_readable = True
    adaptive_swap_sample_count = 0
    adaptive_swap_fallback_count = 0
    previous_heartbeat = -HEARTBEAT_SECONDS
    termination_reason = "natural_exit"
    process_control: dict[str, Any] = {}
    v5_thresholds_enabled = bool(plan.get("v5_fresh_bare_f_authority"))
    c0_thresholds_enabled = c0_enabled
    l2_timeout_decision: dict[str, Any] | None = None
    route_c_enabled = bool(plan.get("v5_route_c"))
    threshold_observation_count = 0
    resource_thresholds: dict[str, Any] = {}
    v8_timeout_decision: dict[str, Any] | None = None
    c0_timeout_decision: dict[str, Any] | None = None
    v8_completed = False
    v9_workflow_completed = False
    s3_workflow_completed = False
    s3_completion: dict[str, Any] | None = None
    if v5_thresholds_enabled or c0_thresholds_enabled:
        resource_thresholds = {
            "preferred": {
                "bytes": int(plan["preferred_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
            "warning": {
                "bytes": int(plan["warning_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
            "hard_stop": {
                "bytes": int(plan["absolute_terminate_memory_bytes"]),
                "crossed": False,
                "first_sample": None,
                "first_elapsed_seconds": None,
            },
        }

    def observe_v5_thresholds(rss_bytes: int, elapsed: float) -> None:
        nonlocal threshold_observation_count
        if not (v5_thresholds_enabled or c0_thresholds_enabled):
            return
        threshold_observation_count += 1
        for threshold in resource_thresholds.values():
            if not threshold["crossed"] and int(rss_bytes) >= int(threshold["bytes"]):
                threshold["crossed"] = True
                threshold["first_sample"] = threshold_observation_count
                threshold["first_elapsed_seconds"] = float(elapsed)

    c0_prelaunch: dict[str, Any] | None = None
    if c0_enabled:
        c0_prelaunch = _v9_c0_prelaunch_resource_preflight()
        if not c0_prelaunch["pass"]:
            failure_path = run_directory / "v9_c0_explicit_coarse_failure.json"
            failure_record = {
                "schema": V9_C0_EXPLICIT_COARSE_ONLY_SCHEMA,
                "method": plan["method"],
                "status": "not_run_by_prelaunch_resource_gate",
                "classification": V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION,
                "next_required_stage": V9_C0_NEXT_C1,
                "numerical_negative": False,
                "process_started": False,
                "resource_preflight": c0_prelaunch,
            }
            failure_path.write_text(
                json.dumps(failure_record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            summary = {
                "schema": "task040.level_a.watchdog.v1",
                "method": plan["method"],
                "source_sha": plan["source_sha"],
                "command": command,
                "termination_reason": "prelaunch_resource_gate",
                "return_code": None,
                "process_started": False,
                "process_control": {"worker_started": False},
                "elapsed_seconds": 0.0,
                "sample_count": 0,
                "authoritative_sample_count": 0,
                "peak_rss_bytes": 0,
                "peak_swap_bytes": 0,
                "peak_dedicated_cgroup_swap_bytes": 0,
                "hard_stop_bytes": hard_stop_bytes,
                "timeout_seconds": timeout_seconds,
                "run_summary_present": False,
                "classification": V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION,
                "resource_classification": V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION,
                "final_resource_classification": (
                    V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION
                ),
                "next_required_stage": V9_C0_NEXT_C1,
                "numerical_negative": False,
                "v9_c0_prelaunch_resource_gate": c0_prelaunch,
                "artifact_hashes": {failure_path.name: _sha256(failure_path)},
            }
            summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return 2

    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        timeline_path.open("w", encoding="utf-8") as timeline,
    ):
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=_worker_environment(),
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            **worker_process_group_popen_kwargs(),
        )
        while True:
            elapsed = time.monotonic() - started
            return_code = process.poll()
            if return_code is not None:
                termination_reason = "natural_exit"
                process_control = terminate_process_tree(process)
                break
            authority = resource_authority_sample(process.pid, include_smaps=False)
            process_tree = authority["process_tree"]
            rss_bytes = int(process_tree["rss_bytes"])
            swap_bytes = int(process_tree["swap_bytes"])
            observe_v5_thresholds(rss_bytes, elapsed)
            job_cgroup = authority["job_cgroup"]
            has_cgroup = bool(job_cgroup["dedicated_job_cgroup"])
            live_sample = bool(process_tree.get("pids"))
            post_sample_return_code = process.poll()
            process_exited_during_sample = post_sample_return_code is not None
            peak_rss_bytes = max(peak_rss_bytes, rss_bytes)
            peak_swap_bytes = max(peak_swap_bytes, swap_bytes)
            dedicated_cgroup_present = dedicated_cgroup_present or has_cgroup
            dedicated_swap = None
            if has_cgroup:
                dedicated_swap = job_cgroup["swap_current_bytes"]
                if dedicated_swap is not None:
                    peak_dedicated_cgroup_swap_bytes = max(
                        peak_dedicated_cgroup_swap_bytes, int(dedicated_swap)
                    )
            stage, status = _latest_stage(stages_path)
            last_stage_status = status
            if stage != last_stage:
                last_stage = stage
                stage_started = time.monotonic()
            completed_cleanup_teardown = _terminal_teardown_sample_excluded(
                post_sample_return_code=post_sample_return_code,
                process_tree=process_tree,
                run_summary_path=run_summary,
                latest_stage=stage,
                latest_stage_status=status,
            )
            terminal_teardown_excluded = (
                process_exited_during_sample or completed_cleanup_teardown
            )
            if (
                adaptive_enabled
                or stage_bc_enabled
                or v9_enabled
                or c0_enabled
                or l2_enabled
            ):
                swap_sample = _v8_adaptive_swap_authority_sample(
                    authority, terminal_excluded=terminal_teardown_excluded
                )
                if swap_sample["counted"]:
                    adaptive_swap_sample_count += 1
                    adaptive_swap_authority_readable = (
                        adaptive_swap_authority_readable
                        and bool(swap_sample["authority_readable"])
                    )
                    if swap_sample["fallback_used"]:
                        adaptive_swap_fallback_count += 1
            authoritative_sample = live_sample and not terminal_teardown_excluded
            if authoritative_sample:
                sample_count += 1
                all_status_readable = all_status_readable and bool(
                    process_tree["all_status_readable"]
                )
                if has_cgroup:
                    dedicated_cgroup_swap_readable = (
                        dedicated_cgroup_swap_readable and dedicated_swap is not None
                    )
            elif terminal_teardown_excluded:
                terminal_teardown_excluded_count += 1
            row = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": elapsed,
                "stage": stage,
                "stage_status": status,
                "rss_bytes": rss_bytes,
                "swap_bytes": swap_bytes,
                "resource_authority": authority,
                "authoritative_sample": authoritative_sample,
                "terminal_teardown_excluded": terminal_teardown_excluded,
                "sample_process_alive_before": True,
                "sample_process_alive_after": not terminal_teardown_excluded,
                "post_sample_return_code": post_sample_return_code,
            }
            _write_jsonl(timeline, row)
            if elapsed - previous_heartbeat >= HEARTBEAT_SECONDS:
                print(
                    "Task040 watchdog heartbeat "
                    f"elapsed={elapsed:.1f}s stage={stage} "
                    f"rss_gib={rss_bytes / 2**30:.3f} swap_bytes={swap_bytes}",
                    flush=True,
                )
                previous_heartbeat = elapsed
            if terminal_teardown_excluded:
                termination_reason = _terminal_teardown_termination_reason(
                    rss_bytes=rss_bytes,
                    swap_bytes=swap_bytes,
                    dedicated_swap_bytes=dedicated_swap,
                    hard_stop_bytes=hard_stop_bytes,
                )
                if process_exited_during_sample or termination_reason != "natural_exit":
                    process_control = terminate_process_tree(process)
                    break
                if elapsed >= timeout_seconds:
                    termination_reason = "wall_timeout"
                    process_control = terminate_process_tree(process)
                    break
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            if not authoritative_sample:
                if elapsed >= timeout_seconds:
                    termination_reason = "wall_timeout"
                    process_control = terminate_process_tree(process)
                    break
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            if rss_bytes >= hard_stop_bytes:
                termination_reason = "absolute_memory_limit"
            elif (
                swap_bytes > SWAP_LIMIT_BYTES
                or peak_dedicated_cgroup_swap_bytes > SWAP_LIMIT_BYTES
            ):
                termination_reason = "swap_detected"
            elif return_code is not None:
                termination_reason = "natural_exit"
            elif elapsed >= timeout_seconds:
                if v8_enabled:
                    timeout_decision = active_timeout(
                        stage,
                        time.monotonic() - stage_started,
                        elapsed,
                    )
                    if l2_enabled:
                        l2_timeout_decision = timeout_decision
                    elif c0_enabled:
                        c0_timeout_decision = timeout_decision
                    else:
                        v8_timeout_decision = timeout_decision
                    if timeout_decision["timed_out"]:
                        termination_reason = (
                            "wall_timeout"
                            if timeout_decision["kind"] == "total"
                            else "v9_c0_marker_target_exceeded"
                            if c0_enabled
                            else "v8_marker_target_exceeded"
                        )
                    else:
                        time.sleep(SAMPLE_INTERVAL_SECONDS)
                        continue
                else:
                    termination_reason = "wall_timeout"
            elif v8_enabled:
                timeout_decision = active_timeout(
                    stage,
                    time.monotonic() - stage_started,
                    elapsed,
                )
                if l2_enabled:
                    l2_timeout_decision = timeout_decision
                elif c0_enabled:
                    c0_timeout_decision = timeout_decision
                else:
                    v8_timeout_decision = timeout_decision
                if timeout_decision["timed_out"]:
                    termination_reason = (
                        "wall_timeout"
                        if timeout_decision["kind"] == "total"
                        else "v9_c0_marker_target_exceeded"
                        if c0_enabled
                        else "v8_marker_target_exceeded"
                    )
                else:
                    time.sleep(SAMPLE_INTERVAL_SECONDS)
                    continue
            else:
                time.sleep(SAMPLE_INTERVAL_SECONDS)
                continue
            process_control = terminate_process_tree(process)
            break

    elapsed_seconds = time.monotonic() - started
    swap_authority_readable = all_status_readable and (
        not dedicated_cgroup_present or dedicated_cgroup_swap_readable
    )
    summary = {
        "schema": "task040.level_a.watchdog.v1",
        "method": plan["method"],
        "source_sha": plan["source_sha"],
        "command": command,
        "termination_reason": termination_reason,
        "return_code": process.returncode,
        "process_control": process_control,
        "elapsed_seconds": elapsed_seconds,
        "sample_count": sample_count,
        "authoritative_sample_count": sample_count,
        "terminal_teardown_excluded_count": terminal_teardown_excluded_count,
        "peak_rss_bytes": peak_rss_bytes,
        "peak_swap_bytes": peak_swap_bytes,
        "peak_dedicated_cgroup_swap_bytes": peak_dedicated_cgroup_swap_bytes,
        "hard_stop_bytes": hard_stop_bytes,
        "timeout_seconds": timeout_seconds,
        "all_status_readable": all_status_readable,
        "dedicated_cgroup_present": dedicated_cgroup_present,
        "dedicated_cgroup_swap_readable": (
            dedicated_cgroup_swap_readable if dedicated_cgroup_present else None
        ),
        "swap_authority_readable": swap_authority_readable,
        "run_summary_present": run_summary.is_file(),
        "run_summary_sha256": _sha256(run_summary) if run_summary.is_file() else None,
        "artifact_hashes": {
            path.name: _sha256(path)
            for path in (stages_path, markers_path, timeline_path, stdout_path)
            if path.is_file()
        },
    }
    if s3_enabled:
        route_kind = "baseline" if s3_j1_enabled else "candidate"
        worker_payload: Mapping[str, Any] | None = None
        if run_summary.is_file():
            try:
                loaded_payload = json.loads(
                    run_summary.read_text(encoding="utf-8")
                )
                if isinstance(loaded_payload, Mapping):
                    worker_payload = loaded_payload
            except (OSError, json.JSONDecodeError):
                worker_payload = None
        s3_resource_gate = bool(
            sample_count > 0
            and all_status_readable
            and peak_rss_bytes < hard_stop_bytes
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and (
                not dedicated_cgroup_present
                or (
                    dedicated_cgroup_swap_readable
                    and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
                )
            )
        )
        s3_completion = _s3_completion_gate(
            route_kind=route_kind,
            termination_reason=termination_reason,
            return_code=process.returncode,
            elapsed_seconds=elapsed_seconds,
            summary_present=worker_payload is not None,
            latest_stage=last_stage,
            latest_stage_status=last_stage_status,
            resource_gate=s3_resource_gate,
            worker_payload=worker_payload,
            resource_limits={
                "hard_stop_bytes": hard_stop_bytes,
                "swap_limit_bytes": SWAP_LIMIT_BYTES,
                "total_wall_seconds": timeout_seconds,
            },
            expected_manifest_path=(
                plan.get("baseline_manifest", {}).get("path")
                if route_kind == "candidate"
                and isinstance(plan.get("baseline_manifest"), Mapping)
                else None
            ),
            expected_manifest_sha256=(
                plan.get("baseline_manifest", {}).get("sha256")
                if route_kind == "candidate"
                and isinstance(plan.get("baseline_manifest"), Mapping)
                else None
            ),
            expected_input_path=plan.get("input"),
            expected_input_sha256=(
                plan.get("input_expected", {}).get("sha256")
                if isinstance(plan.get("input_expected"), Mapping)
                else None
            ),
            expected_source_sha=plan.get("source_sha"),
        )
        s3_workflow_completed = bool(s3_completion["workflow_completed"])
        worker_classification = s3_completion["worker_classification"]
        if termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
        }:
            s3_classification = "S3B_RESOURCE_UNAVAILABLE"
        elif worker_payload is None or process.returncode != 0:
            if isinstance(worker_classification, str) and worker_classification:
                s3_classification = worker_classification
            else:
                s3_classification = "requires_result_adjudication"
        elif not s3_completion["resource_gate"] or not s3_completion[
            "wall_time_gate"
        ]:
            s3_classification = "S3B_RESOURCE_UNAVAILABLE"
        elif isinstance(worker_classification, str) and worker_classification:
            s3_classification = worker_classification
        else:
            s3_classification = "requires_result_adjudication"
        summary.update(
            {
                "s3_route_kind": route_kind,
                "s3_workflow_completed": s3_workflow_completed,
                "s3_baseline_manifest_usable": s3_completion[
                    "baseline_manifest_usable"
                ],
                "s3_candidate_outcome_ready": s3_completion[
                    "candidate_outcome_ready"
                ],
                "s3_worker_schema": s3_completion["worker_schema"],
                "s3_worker_classification": worker_classification,
                "s3_worker_next_stage": s3_completion["worker_next_stage"],
                "s3_worker_error": s3_completion["worker_error"],
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "s3_resource_gate": s3_resource_gate,
                "s3_wall_time_gate": s3_completion["wall_time_gate"],
                "s3_wall_time_check": {
                    "elapsed_seconds": elapsed_seconds,
                    "limit_seconds": timeout_seconds,
                    "within_limit": s3_completion["wall_time_gate"],
                },
                "s3_resource_limits": s3_completion["resource_limits"],
                "s3_completion_checks": {
                    "common": s3_completion["common_checks"],
                    "route": s3_completion["route_checks"],
                },
                "classification": s3_classification,
                "resource_classification": s3_classification,
                "final_resource_classification": s3_classification,
            }
        )
    if c0_enabled:
        c0_manifest = worker_directory / "v9_c0_explicit_coarse_manifest.json"
        c0_failure_manifest = (
            worker_directory / "v9_c0_explicit_coarse_failure_manifest.json"
        )
        worker_payload: dict[str, Any] = {}
        cleanup_complete = False
        core_cleanup_complete = False
        if run_summary.is_file():
            try:
                worker_payload = json.loads(run_summary.read_text(encoding="utf-8"))
                runner_cleanup = worker_payload.get("runner_cleanup", {})
                core_cleanup = worker_payload.get("cleanup", {})
                cleanup_complete = bool(
                    isinstance(runner_cleanup, dict)
                    and runner_cleanup.get("status") == "complete"
                )
                core_cleanup_complete = bool(
                    isinstance(core_cleanup, dict)
                    and core_cleanup.get("status") == "complete"
                )
            except (OSError, json.JSONDecodeError):
                worker_payload = {}
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v9_c0_marker_target_exceeded",
        }
        c0_resource_gate = bool(
            sample_count > 0
            and adaptive_swap_authority_readable
            and all_status_readable
            and peak_rss_bytes < V9_C0_HARD_STOP_BYTES
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and (
                not dedicated_cgroup_present
                or (
                    dedicated_cgroup_swap_readable
                    and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
                )
            )
        )
        c0_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and core_cleanup_complete
            and c0_manifest.is_file()
            and last_stage == "v9_c0_cleanup_complete"
            and last_stage_status == "complete"
        )
        worker_classification = worker_payload.get("classification")
        valid_worker_classifications = {
            "ADAPTIVE_COARSE_CONTENT_POSITIVE_EXPLICIT_ORACLE",
            "CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL",
            V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION,
        }
        if resource_stop or (c0_workflow_completed and not c0_resource_gate):
            c0_classification = V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION
        elif c0_failure_manifest.is_file():
            c0_classification = "V9_C0_EXPLICIT_COARSE_IMPLEMENTATION_FAILURE"
        elif (
            (
                termination_reason == "natural_exit"
                and run_summary.is_file()
                and worker_classification
                == V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION
            )
            or (
                c0_workflow_completed
                and worker_classification in valid_worker_classifications
            )
        ):
            c0_classification = worker_classification
        else:
            c0_classification = "requires_result_adjudication"
        if c0_classification == "CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL":
            c0_next_stage = V9_C0_NEXT_E
            c0_numerical_negative = True
        elif (
            c0_classification
            == "ADAPTIVE_COARSE_CONTENT_POSITIVE_EXPLICIT_ORACLE"
            or c0_classification == V9_C0_RESOURCE_UNAVAILABLE_CLASSIFICATION
        ):
            c0_next_stage = V9_C0_NEXT_C1
            c0_numerical_negative = False
        else:
            c0_next_stage = None
            c0_numerical_negative = None
        c0_resource_thresholds = {
            name: dict(value) for name, value in resource_thresholds.items()
        }
        summary.update(
            {
                "v9_c0_workflow_completed": c0_workflow_completed,
                "v9_c0_manifest_present": c0_manifest.is_file(),
                "v9_c0_manifest_sha256": (
                    _sha256(c0_manifest) if c0_manifest.is_file() else None
                ),
                "v9_c0_resource_gate": c0_resource_gate,
                "v9_c0_prelaunch_resource_gate": c0_prelaunch,
                "v9_c0_resource_thresholds": c0_resource_thresholds,
                "v9_c0_marker_sequence": list(V9_C0_MARKER_SEQUENCE),
                "v9_c0_source_contract": {
                    "source_order": ["external_dtn_coupling"],
                    "global_patch_count": 630,
                    "columns_per_patch": 160,
                    "total_coarse_dof": 100800,
                },
                "v9_c0_cleanup_complete": cleanup_complete and core_cleanup_complete,
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "classification": c0_classification,
                "resource_classification": c0_classification,
                "final_resource_classification": c0_classification,
                "next_required_stage": c0_next_stage,
                "numerical_negative": c0_numerical_negative,
                "v9_c0_resource_limits": {
                    "minimum_mem_available_bytes": V9_C0_MIN_AVAILABLE_BYTES,
                    "preferred_memory_bytes": V9_C0_PREFERRED_MEMORY_BYTES,
                    "warning_memory_bytes": V9_C0_WARNING_MEMORY_BYTES,
                    "hard_stop_bytes": V9_C0_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "setup_seconds": V9_C0_SETUP_TARGET_SECONDS,
                    "one_apply_seconds": V9_C0_ONE_APPLY_TARGET_SECONDS,
                    "total_wall_seconds": V9_C0_TIMEOUT_SECONDS,
                },
                "v9_c0_timeout": c0_timeout_decision,
            }
        )
    elif l2_enabled:
        worker_payload: Mapping[str, Any] | None = None
        if run_summary.is_file():
            try:
                loaded_payload = json.loads(
                    run_summary.read_text(encoding="utf-8")
                )
                if isinstance(loaded_payload, Mapping):
                    worker_payload = loaded_payload
            except (OSError, json.JSONDecodeError):
                worker_payload = None
        l2_resource_gate = bool(
            adaptive_swap_sample_count > 0
            and adaptive_swap_authority_readable
            and peak_rss_bytes < hard_stop_bytes
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and (
                not dedicated_cgroup_present
                or (
                    dedicated_cgroup_swap_readable
                    and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
                )
            )
        )
        l2_worker_status = (
            worker_payload.get("status")
            if isinstance(worker_payload, Mapping)
            else None
        )
        l2_worker_classification = (
            worker_payload.get("classification")
            if isinstance(worker_payload, Mapping)
            else None
        )
        l2_valid_status = l2_worker_status in {
            "V9_E_LOR_L2_ONLY_ACTION_PASS",
            "V9_E_LOR_L2_ONLY_ACTION_FAIL",
        }
        if l2_worker_classification is None and l2_valid_status:
            l2_worker_classification = l2_worker_status
        l2_valid_classification = l2_worker_classification in {
            "V9_E_LOR_L2_ONLY_ACTION_PASS",
            "V9_E_LOR_L2_ONLY_ACTION_FAIL",
        }
        l2_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and worker_payload is not None
            and l2_valid_status
            and last_stage == "v9_e_lor_l2_cleanup_complete"
            and last_stage_status == "complete"
        )
        l2_resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
        }
        if l2_resource_stop or not l2_resource_gate:
            l2_numerical_classification = "V9_E_LOR_L2_RESOURCE_UNAVAILABLE"
            l2_resource_classification = "V9_E_LOR_L2_RESOURCE_UNAVAILABLE"
            l2_numerical_negative = False
        elif l2_workflow_completed and l2_valid_classification:
            l2_numerical_classification = str(l2_worker_classification)
            l2_resource_classification = "resource_gate_pass"
            l2_numerical_negative = l2_numerical_classification.endswith("_FAIL")
        else:
            l2_numerical_classification = "requires_result_adjudication"
            l2_resource_classification = "requires_resource_adjudication"
            l2_numerical_negative = None
        summary.update(
            {
                "v9_e_lor_l2_workflow_completed": l2_workflow_completed,
                "v9_e_lor_l2_worker_status": l2_worker_status,
                "v9_e_lor_l2_worker_classification": (
                    l2_worker_classification
                ),
                "v9_e_lor_l2_resource_gate": l2_resource_gate,
                "adaptive_swap_sample_count": adaptive_swap_sample_count,
                "adaptive_swap_fallback_count": adaptive_swap_fallback_count,
                "v9_e_lor_l2_cleanup_complete": (
                    last_stage == "v9_e_lor_l2_cleanup_complete"
                    and last_stage_status == "complete"
                ),
                "v9_e_lor_l2_marker_sequence": list(
                    V9_E_LOR_L2_MARKER_SEQUENCE
                ),
                "v9_e_lor_l2_timeout": l2_timeout_decision,
                "v9_e_lor_l2_resource_limits": {
                    "hard_stop_bytes": V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "total_wall_seconds": V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS,
                },
                "classification": l2_numerical_classification,
                "resource_classification": l2_resource_classification,
                "final_resource_classification": l2_resource_classification,
                "next_required_stage": "V9_E_LOR_L2_TWO_CASE_REVIEW",
                "numerical_negative": l2_numerical_negative,
            }
        )
    elif v9_enabled:
        v9_manifest = worker_directory / "v9_source_bridge_manifest.json"
        v9_failure_manifest = (
            worker_directory / "v9_source_bridge_failure_manifest.json"
        )
        worker_payload: dict[str, Any] = {}
        cleanup_complete = False
        if run_summary.is_file():
            try:
                worker_payload = json.loads(run_summary.read_text(encoding="utf-8"))
                cleanup_complete = bool(
                    worker_payload.get("cleanup", {}).get("status") == "complete"
                )
            except (OSError, json.JSONDecodeError):
                worker_payload = {}
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        resource_gate = bool(
            sample_count > 0
            and adaptive_swap_authority_readable
            and peak_rss_bytes < V8_ADAPTIVE_HARD_STOP_BYTES
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and (
                not dedicated_cgroup_present
                or (
                    dedicated_cgroup_swap_readable
                    and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
                )
            )
        )
        v9_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and v9_manifest.is_file()
            and last_stage == "v9_source_bridge_cleanup_complete"
            and last_stage_status == "complete"
        )
        worker_classification = worker_payload.get("classification")
        if worker_classification is None and worker_payload.get("status") == (
            "verified_source_canonical_bridge"
        ):
            worker_classification = "V9_SOURCE_CANONICAL_BRIDGE_PASS"
        valid_worker_classifications = {
            "V9_SOURCE_CANONICAL_BRIDGE_PASS",
            "V9_SOURCE_CANONICAL_BRIDGE_IDENTITY_UNAVAILABLE",
            "V9_SOURCE_CANONICAL_BRIDGE_IMPLEMENTATION_FAILURE",
        }
        if resource_stop:
            v9_classification = "V9_SOURCE_CANONICAL_BRIDGE_RESOURCE_UNAVAILABLE"
        elif v9_failure_manifest.is_file():
            v9_classification = "V9_SOURCE_CANONICAL_BRIDGE_IMPLEMENTATION_FAILURE"
        elif v9_workflow_completed and not resource_gate:
            v9_classification = "V9_SOURCE_CANONICAL_BRIDGE_RESOURCE_UNAVAILABLE"
        elif v9_workflow_completed and worker_classification in valid_worker_classifications:
            v9_classification = worker_classification
        else:
            v9_classification = "requires_result_adjudication"
        summary.update(
            {
                "v9_source_bridge_workflow_completed": v9_workflow_completed,
                "v9_source_bridge_manifest_present": v9_manifest.is_file(),
                "v9_source_bridge_manifest_sha256": (
                    _sha256(v9_manifest) if v9_manifest.is_file() else None
                ),
                "v9_source_bridge_resource_gate": resource_gate,
                "v9_source_bridge_signal_positive": False,
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": v9_classification,
                "final_resource_classification": v9_classification,
                "v9_source_bridge_resource_limits": {
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "total_wall_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                },
            }
        )
    elif stage_bc_enabled:
        stage_bc_manifest = worker_directory / "v8_adaptive_stage_bc_manifest.json"
        stage_bc_failure_manifest = (
            worker_directory / "v8_adaptive_stage_bc_failure_manifest.json"
        )
        worker_payload: dict[str, Any] = {}
        cleanup_complete = False
        if run_summary.is_file():
            try:
                worker_payload = json.loads(run_summary.read_text(encoding="utf-8"))
                cleanup_complete = bool(
                    worker_payload.get("cleanup", {}).get("status") == "complete"
                )
            except (OSError, json.JSONDecodeError):
                worker_payload = {}
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        resource_gate = bool(
            sample_count > 0
            and adaptive_swap_authority_readable
            and peak_rss_bytes < V8_ADAPTIVE_HARD_STOP_BYTES
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and (
                not dedicated_cgroup_present
                or (
                    dedicated_cgroup_swap_readable
                    and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
                )
            )
        )
        stage_bc_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and stage_bc_manifest.is_file()
            and last_stage == "v8_adaptive_stage_bc_cleanup_complete"
            and last_stage_status == "complete"
        )
        worker_classification = worker_payload.get("classification")
        valid_worker_classifications = {
            "ADAPTIVE_SPECTRAL_SCHWARZ_POSITIVE_AT_H4",
            "ADAPTIVE_SPECTRAL_SCHWARZ_NO_SIGNAL_AT_H4",
            "ADAPTIVE_SPECTRAL_SCHWARZ_UNSTABLE_AT_H4",
            "ADAPTIVE_SPECTRAL_SCHWARZ_INCONCLUSIVE_AT_H4",
            "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE",
            "V8_ADAPTIVE_STAGE_BC_IMPLEMENTATION_FAILURE",
        }
        if resource_stop:
            stage_bc_classification = "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
        elif stage_bc_failure_manifest.is_file():
            stage_bc_classification = "V8_ADAPTIVE_STAGE_BC_IMPLEMENTATION_FAILURE"
        elif stage_bc_workflow_completed and not resource_gate:
            stage_bc_classification = "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
        elif stage_bc_workflow_completed and worker_classification in valid_worker_classifications:
            stage_bc_classification = worker_classification
        else:
            stage_bc_classification = "requires_result_adjudication"
        signal_positive = bool(
            stage_bc_workflow_completed
            and resource_gate
            and stage_bc_classification
            == "ADAPTIVE_SPECTRAL_SCHWARZ_POSITIVE_AT_H4"
        )
        summary.update(
            {
                "v8_adaptive_stage_bc_workflow_completed": (
                    stage_bc_workflow_completed
                ),
                "v8_adaptive_stage_bc_manifest_present": stage_bc_manifest.is_file(),
                "v8_adaptive_stage_bc_manifest_sha256": (
                    _sha256(stage_bc_manifest)
                    if stage_bc_manifest.is_file()
                    else None
                ),
                "v8_adaptive_stage_bc_resource_gate": resource_gate,
                "v8_adaptive_stage_bc_signal_positive": signal_positive,
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": stage_bc_classification,
                "final_resource_classification": stage_bc_classification,
                "v8_adaptive_stage_bc_resource_limits": {
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                    "total_wall_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                },
            }
        )
    elif stage_a_enabled:
        cleanup_complete = False
        local_gate_pass: bool | None = None
        if run_summary.is_file():
            try:
                cleanup_payload = json.loads(run_summary.read_text(encoding="utf-8"))
                cleanup_complete = bool(
                    cleanup_payload.get("cleanup", {}).get("status") == "complete"
                )
                if "local_gate_pass" in cleanup_payload:
                    local_gate_pass = bool(cleanup_payload["local_gate_pass"])
            except (OSError, json.JSONDecodeError):
                cleanup_complete = False
        adaptive_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and last_stage == "v8_adaptive_cleanup_complete"
            and last_stage_status == "complete"
        )
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        preferred_peak_pass = peak_rss_bytes <= V8_ADAPTIVE_PREFERRED_MEMORY_BYTES
        swap_gate = bool(
            adaptive_swap_authority_readable
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
        )
        resource_gate = bool(preferred_peak_pass and swap_gate)
        if resource_stop:
            adaptive_classification = V8_ADAPTIVE_RESOURCE_UNAVAILABLE_CLASSIFICATION
        elif adaptive_workflow_completed and not resource_gate:
            adaptive_classification = "ADAPTIVE_STAGE_A_RESOURCE_NEGATIVE"
        elif adaptive_workflow_completed and local_gate_pass is False:
            adaptive_classification = "ADAPTIVE_STAGE_A_NUMERICAL_LOCAL_GATE_NEGATIVE"
        elif (
            adaptive_workflow_completed
            and local_gate_pass is True
            and resource_gate
        ):
            adaptive_classification = "ADAPTIVE_STAGE_A_VIABILITY_PASS"
        else:
            adaptive_classification = "requires_result_adjudication"
        summary.update(
            {
                "v8_adaptive_workflow_completed": adaptive_workflow_completed,
                "v8_adaptive_viability_pass": bool(
                    adaptive_workflow_completed
                    and local_gate_pass is True
                    and resource_gate
                ),
                "v8_adaptive_local_gate": (
                    local_gate_pass
                    if local_gate_pass is not None
                    else "pending_runner_result"
                ),
                "v8_adaptive_resource_gate": resource_gate,
                "preferred_peak_pass": preferred_peak_pass,
                "swap_gate": swap_gate,
                "adaptive_swap_authority_readable": (
                    adaptive_swap_authority_readable
                ),
                "adaptive_swap_sample_count": adaptive_swap_sample_count,
                "adaptive_swap_fallback_count": adaptive_swap_fallback_count,
                "adaptive_swap_authority_semantics": (
                    "complete process-tree VmSwap; nonterminal incomplete tree "
                    "may use readable non-dedicated cgroup memory.swap.current==0 "
                    "as a superset zero upper bound; terminal teardown excluded"
                ),
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": adaptive_classification,
                "final_resource_classification": adaptive_classification,
                "v8_adaptive_stage_timeout": v8_timeout_decision,
                "v8_adaptive_resource_limits": {
                    "setup_no_marker_seconds": V8_ADAPTIVE_SETUP_TARGET_SECONDS,
                    "one_apply_hard_seconds": V8_ADAPTIVE_ONE_APPLY_TARGET_SECONDS,
                    "total_wall_seconds": V8_ADAPTIVE_TIMEOUT_SECONDS,
                    "preferred_memory_bytes": V8_ADAPTIVE_PREFERRED_MEMORY_BYTES,
                    "hard_stop_bytes": V8_ADAPTIVE_HARD_STOP_BYTES,
                    "swap_limit_bytes": SWAP_LIMIT_BYTES,
                },
            }
        )
    elif b1_enabled:
        b1_manifest = worker_directory / "v8_adaptive_stage_b1_manifest.json"
        try:
            cleanup_complete = bool(
                json.loads(run_summary.read_text(encoding="utf-8"))
                .get("cleanup", {})
                .get("status")
                == "complete"
            ) if run_summary.is_file() else False
        except (OSError, json.JSONDecodeError):
            cleanup_complete = False
        b1_workflow_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and run_summary.is_file()
            and cleanup_complete
            and b1_manifest.is_file()
            and last_stage == "v8_adaptive_stage_b1_cleanup_complete"
            and last_stage_status == "complete"
            and adaptive_swap_authority_readable
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
        )
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        b1_classification = (
            "ADAPTIVE_STAGE_B1_RESOURCE_UNAVAILABLE"
            if resource_stop
            else "ADAPTIVE_STAGE_B1_WORKFLOW_COMPLETED"
            if b1_workflow_completed
            else "requires_result_adjudication"
        )
        summary.update(
            {
                "v8_adaptive_stage_b1_workflow_completed": (
                    b1_workflow_completed
                ),
                "v8_adaptive_stage_b1_manifest_present": b1_manifest.is_file(),
                "v8_adaptive_stage_b1_manifest_sha256": (
                    _sha256(b1_manifest) if b1_manifest.is_file() else None
                ),
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": b1_classification,
                "final_resource_classification": b1_classification,
            }
        )
    elif v8_enabled:
        v8_completed = bool(
            termination_reason == "natural_exit"
            and process.returncode == 0
            and last_stage == "v8_full_spectrum_cleanup_complete"
            and last_stage_status == "complete"
        )
        resource_stop = termination_reason in {
            "absolute_memory_limit",
            "swap_detected",
            "wall_timeout",
            "v8_marker_target_exceeded",
        }
        v8_resource_classification = (
            "v8_completed"
            if v8_completed
            else (
                V8_RESOURCE_UNAVAILABLE_CLASSIFICATION
                if resource_stop
                else "requires_result_adjudication"
            )
        )
        summary.update(
            {
                "v8_completed": v8_completed,
                "latest_stage": last_stage,
                "latest_stage_status": last_stage_status,
                "resource_classification": v8_resource_classification,
                "final_resource_classification": v8_resource_classification,
                "v8_stage_timeout": v8_timeout_decision,
                "v8_resource_limits": {
                    "setup_or_factor_no_marker_seconds": (
                        V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS
                        if v9_corrected_full_enabled
                        else 2 * V8_FULL_SPECTRUM_SETUP_TARGET_SECONDS
                    ),
                    "transform_or_symbol_no_marker_seconds": (
                        V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
                        if v9_corrected_full_enabled
                        else 2 * V8_FULL_SPECTRUM_TRANSFORM_TARGET_SECONDS
                    ),
                    "one_apply_hard_seconds": (
                        V8_FULL_SPECTRUM_ONE_APPLY_TARGET_SECONDS
                    ),
                    "total_wall_seconds": V8_FULL_SPECTRUM_TIMEOUT_SECONDS,
                    "minimum_mem_available_bytes": (
                        96 * 2**30 if v9_corrected_full_enabled else None
                    ),
                    "corrected_source_packet": v9_corrected_full_enabled,
                },
            }
        )
    if v5_thresholds_enabled:
        peak = int(peak_rss_bytes)
        if peak >= int(plan["absolute_terminate_memory_bytes"]):
            resource_classification = "hard_stop_threshold_crossed"
        elif peak >= int(plan["warning_memory_bytes"]):
            resource_classification = "warning_threshold_crossed"
        elif peak >= int(plan["preferred_memory_bytes"]):
            resource_classification = "preferred_threshold_crossed"
        else:
            resource_classification = "within_preferred_threshold"
        summary.update(
            {
                "preferred_memory_bytes": int(plan["preferred_memory_bytes"]),
                "warning_memory_bytes": int(plan["warning_memory_bytes"]),
                "hard_stop_bytes": int(plan["absolute_terminate_memory_bytes"]),
                "resource_thresholds": resource_thresholds,
                "resource_threshold_observation_count": threshold_observation_count,
                "resource_classification": resource_classification,
                "final_resource_classification": resource_classification,
            }
        )
    elif route_c_enabled:
        route_c_hard_stop = int(plan["absolute_terminate_memory_bytes"])
        if termination_reason == "absolute_memory_limit":
            resource_classification = "route_c_hard_stop_threshold_crossed"
        elif termination_reason == "swap_detected":
            resource_classification = "route_c_swap_blocked"
        elif termination_reason == "wall_timeout":
            resource_classification = "route_c_wall_timeout"
        else:
            resource_classification = "route_c_within_45_gib_hard_line"
        summary.update(
            {
                "route_c_hard_stop_bytes": route_c_hard_stop,
                "route_c_swap_limit_bytes": SWAP_LIMIT_BYTES,
                "route_c_timeout_seconds": TASK040_LEVEL_A_TIMEOUT_SECONDS,
                "route_c_resource_classification": resource_classification,
                "resource_classification": resource_classification,
                "final_resource_classification": resource_classification,
                "route_c_hard_stop_crossed": bool(peak_rss_bytes >= route_c_hard_stop),
                "route_c_peak_memory_bytes": int(peak_rss_bytes),
            }
        )
    elif plan.get("packet_producer") is True:
        summary["preferred_memory_bytes"] = int(plan["preferred_memory_bytes"])
    final_swap_authority_readable = (
        adaptive_swap_authority_readable
        if (
            adaptive_enabled
            or stage_bc_enabled
            or v9_enabled
            or c0_enabled
            or l2_enabled
        )
        else swap_authority_readable
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    completed_gate = (
        s3_workflow_completed
        if s3_enabled
        else adaptive_workflow_completed
        if stage_a_enabled
        else b1_workflow_completed
        if b1_enabled
        else l2_workflow_completed
        if l2_enabled
        else c0_workflow_completed
        if c0_enabled
        else v9_workflow_completed
        if v9_enabled
        else stage_bc_workflow_completed
        if stage_bc_enabled
        else v8_completed
        if v8_enabled
        else (process.returncode == 0 and termination_reason == "natural_exit")
    )
    return (
        0
        if (
            completed_gate
            and run_summary.is_file()
            and final_swap_authority_readable
            and peak_swap_bytes == SWAP_LIMIT_BYTES
            and peak_dedicated_cgroup_swap_bytes == SWAP_LIMIT_BYTES
        )
        else 2
    )


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
    parser.add_argument(V9_E_S3_J1_BASELINE_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_E_S3_STRUCTURED_B1_ONLY_FLAG, action="store_true")
    parser.add_argument(V9_E_S3_J1_BASELINE_MANIFEST_OPTION)
    parser.add_argument(V9_E_S3_J1_BASELINE_MANIFEST_SHA256_OPTION)
    parser.add_argument(V9_SOURCE_PACKET_ROOT_OPTION)
    parser.add_argument(V9_SOURCE_PACKET_MANIFEST_SHA256_OPTION)
    parser.add_argument("--watchdog-enabled", action="store_true")
    parser.add_argument("--bottom-route-only", action="store_true")
    parser.add_argument("--interface-packet-root")
    args = parser.parse_args(argv)
    if args.v5_route_c and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "Route C requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v6_2_interface_schur and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V6-2 interface Schur requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v8_adaptive_schwarz_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V8 adaptive route requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v8_adaptive_stage_b1_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V8 adaptive Stage-B1 route requires "
            "--watchdog-enabled and --bottom-route-only"
        )
    if args.v8_adaptive_stage_bc_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V8 adaptive Stage-B/C route requires "
            "--watchdog-enabled and --bottom-route-only"
        )
    if args.v9_source_bridge_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V9 source bridge route requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v9_c0_explicit_coarse_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V9-C0 route requires --watchdog-enabled and --bottom-route-only"
        )
    if args.v9_e_lor_l2_only and not (
        args.watchdog_enabled and args.bottom_route_only
    ):
        parser.error(
            "V9-E L2 route requires --watchdog-enabled and --bottom-route-only"
        )
    if (
        args.v9_e_s3_j1_baseline_only or args.v9_e_s3_structured_b1_only
    ) and not (args.watchdog_enabled and args.bottom_route_only):
        parser.error(
            "V9-E S3 route requires --watchdog-enabled and --bottom-route-only"
        )
    plan = build_task040_level_a_watchdog_plan(
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
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    return run_task040_level_a_watchdog(plan)


if __name__ == "__main__":
    raise SystemExit(main())
