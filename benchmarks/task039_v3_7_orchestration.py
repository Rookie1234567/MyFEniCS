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
from types import SimpleNamespace
from collections.abc import Callable, Mapping
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
    create_research_exact_side_lu_block_ldu_preconditioner,
)
from src.solvers.common_3d_solve import _petsc_matrix_stats
from src.solvers.hybrid_local_dtn_action import (
    create_hybrid_local_dtn_action_components,
)
from src.solvers.hybrid_local_dtn_woodbury import (
    HybridLocalDtnWoodburyFixedAction,
    HybridLocalDtnWoodburyFixedBudgetKrylovAction,
    MUMPS_BLR_V5_H4_PROFILE,
    create_research_exact_side_lu_action,
)
from src.solvers.hybrid_side_subspace_correction import (
    build_fixed_side_error_subspace_correction_action,
)
from src.solvers.hybrid_whole_endcap_fixed_smoother import (
    build_hybrid_whole_endcap_fixed_smoother_action,
)


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
V5_H4_BLR_SIDE_SETUP_PEAK_LIMIT_GIB = 59.7638938904
V5_H4_BLR_RHS_SPECS = (
    ("physical_side_rhs", "system_rhs", None),
    ("modal_traction_positive", "positive_traction", 761),
    ("modal_traction_negative", "negative_traction", 763),
    ("external_dtn_coupling", "C", 769),
    ("fixed_random_repeat_0", "random", 773),
    ("fixed_random_repeat_1", "random", 779),
)


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
    return {
        "columns": columns,
        "roles": {str(column): list(roles[str(column)]) for column in columns},
        "sha256": actual_sha,
        "manifest_sha256": packet["manifest_sha256"],
        "identity_sha256": packet.get("identity_sha256"),
        "path": str(Path(path)),
    }


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
    payload: Mapping[str, Any], *, poll_interval_seconds: float = V3_7_POLL_SECONDS
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
    return {
        "warning_memory_gib": V3_7_WARNING_GIB,
        "critical_memory_gib": V3_7_CRITICAL_GIB,
        "critical_action": "record_checkpoint_only",
        "absolute_terminate_memory_bytes": V3_7_ABSOLUTE_HARD_BYTES,
        "absolute_hard_stop_action": "terminate_complete_process_tree",
        "require_zero_swap": True,
        "poll_interval_seconds": float(poll_interval_seconds),
        "hard_stop_gib": V3_7_ABSOLUTE_HARD_BYTES / 2**30,
    }


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
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Describe the opt-in worker command consumed by the existing watchdog."""

    if v5_h4_setup_only or v5_h4_blr_side_only:
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
    policy = v3_7_watchdog_policy(payload)
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
            )
        )
        > 1
    ):
        raise ValueError(
            "Candidate routes, V5 h4 setup-only, and V5 h4 BLR side routes are exclusive"
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
    if v5_h4_setup_only or v5_h4_blr_side_only:
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
                (
                    "--v5-h4-setup-only"
                    if v5_h4_setup_only
                    else "--v5-h4-blr-side-component"
                ),
                "--selected-mode-packet-manifest",
                str(Path(selected_mode_packet_manifest).resolve()),
                "--selected-mode-packet-identity",
                str(Path(selected_mode_packet_identity).resolve()),
                "--selected-mode-packet-manifest-sha256",
                str(selected_mode_packet_manifest_sha256),
            ]
        )
    if v5_h4_setup_only:
        method = "task039_v5_h4_exact_side_setup_only"
    elif v5_h4_blr_side_only:
        method = V5_H4_BLR_SIDE_METHOD
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
    return {
        "argv": argv,
        "shell": False,
        "launcher": "src.runners.task038_launcher",
        "watchdog": policy,
        "worker_contract": {
            "mpi_size": 8,
            "profile_id": (
                "task039.v5.h4.exact-side.setup-only.v1"
                if v5_h4_setup_only
                else (
                    V5_H4_BLR_SIDE_PROFILE_ID
                    if v5_h4_blr_side_only
                    else V3_7_PROFILE_ID
                )
            ),
            "method": method,
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
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: str | Path | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run the opt-in child through Task38's existing process-tree watchdog."""

    if v5_h4_setup_only or v5_h4_blr_side_only:
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
        and not V3_7_DIRECT_RUN_ROOT.is_dir()
    ):
        raise ValueError("V3-7 direct producer inventory is unavailable")
    if not v5_h4_blr_side_only and not callable(
        compare_v3_7_hybrid_candidate_to_direct
    ):
        raise ValueError("V3-7 integrated checker entry point is unavailable")
    if len(source_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_sha.lower()
    ):
        raise ValueError("V3-7 source_sha must be a full hexadecimal commit SHA")
    if (
        not v5_h4_setup_only
        and not v5_h4_blr_side_only
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
) -> dict[str, Any]:
    """Run the fixed research-only exact-reference/BLR side component."""

    side_reports: dict[str, Any] = {}
    all_reports: list[dict[str, Any]] = []
    contract = {
        "profile": V5_H4_BLR_SIDE_PROFILE_ID,
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
        exact_components = _build_research_explicit_side_components(system)
        exact_action = None
        exact_probe_reports: list[dict[str, Any]] = []
        exact_artifacts: dict[str, dict[str, Any]] = {}
        exact_diagnostics: dict[str, Any] = {}
        exact_cleanup: dict[str, Any] = {}
        try:
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
            if exact_action is not None:
                exact_cleanup = _v5_blr_destroy_side(
                    exact_action, exact_components, comm
                )
            else:
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
            expected_profile=MUMPS_BLR_V5_H4_PROFILE,
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
                compressed_factor_profile=MUMPS_BLR_V5_H4_PROFILE,
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
                rhs = None
                reference = None
                try:
                    rhs = _load_v5_blr_reference_spool(
                        artifacts["rhs"], action.operator
                    )
                    reference = _load_v5_blr_reference_spool(
                        artifacts["exact_output"], action.operator
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
        "mumps_controls": {"icntl_35": 1, "cntl_7": 1.0e-5, "icntl_14": 80},
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


def run_v5_h4_exact_side_setup_only(
    setup: Any,
    layout: HybridAugmentedLayout,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    qualification_scope: str = TASK039_V4_H4_CASE_QUALIFICATION_SCOPE,
    sampled_column_contract: Mapping[str, Any] | None = None,
    streaming_w_batch_size: int | None = None,
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
    try:
        sampled_column_contract = (
            _load_v5_h4_sampled_column_contract()
            if sampled_column_contract is None
            else dict(sampled_column_contract)
        )
        post_coupling_cleanup = collective_heap_cleanup(comm)
        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            side_components = _build_research_explicit_side_components(system)
            components[side] = side_components
            _emit_marker(
                marker_callback,
                f"{side}_F_ready",
                source="research_explicit_side_components",
                matrices=_v5_side_matrix_inventory(side_components),
                retained_through_woodbury_build=True,
                original_F_retained_for_modal_schur=False,
                post_coupling_cleanup=post_coupling_cleanup,
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
        )
        completed = True
        result = {
            "schema": "task039.v5-h4-exact-side-setup-only.v1",
            "status": "setup_only_completed",
            "qualification_scope": qualification_scope,
            "sampled_column_contract": sampled_column_contract,
            "markers": list(V5_H4_SETUP_ONLY_MARKERS),
            "solve": "not_run",
            "recovery": "not_run",
            "field_export": "not_run",
            "side_actions": {
                side: action.diagnostics for side, action in actions.items()
            },
            "modal_schur": context.inventory.get("modal_schur"),
            "outer_ksp": {
                "type": str(ksp.getType()),
                "restart": 10,
                "ksp_profile": "v5_exact_side_fixed_pc_gmres10",
                "set_up": True,
                "solve_called": False,
                "krylov_vectors": "not_allocated_before_solve",
            },
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
    selected_mode_packet_manifest: str | Path | None = None,
    selected_mode_packet_identity: Mapping[str, Any] | None = None,
    selected_mode_packet_manifest_sha256: str | None = None,
    v5_sampled_column_contract: Mapping[str, Any] | None = None,
    v5_streaming_w_batch_size: int | None = None,
) -> dict[str, Any]:
    """Prepare the V3-7 campaign or an explicit research candidate branch."""

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

    try:
        _emit_marker(marker_callback, "diagnostic_entry")
        profile = None
        if not v5_h4_setup_only and not v5_h4_blr_side_only:
            profile = (
                profile_override
                if profile_override is not None
                else v3_7_profile_from_resolved(resolved_payload)
            )
        if v5_h4_setup_only or v5_h4_blr_side_only:
            incidence = resolved_payload["incidence"]
            profile = replace(
                make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0),
                profile_id=(
                    "task039.v5.h4.exact-side.setup-only.v1"
                    if v5_h4_setup_only
                    else V5_H4_BLR_SIDE_PROFILE_ID
                ),
                record_schema=(
                    "task039.v5.h4.exact-side.setup-only.v1"
                    if v5_h4_setup_only
                    else V5_H4_BLR_SIDE_PROFILE_ID
                ),
                qualification_schema=(
                    "task039.v5.h4.exact-side.setup-only.v1"
                    if v5_h4_setup_only
                    else V5_H4_BLR_SIDE_PROFILE_ID
                ),
                wavelength_nm=float(incidence["wavelength_nm"]),
                incident_grazing_deg=float(incidence["grazing_angle_deg"]),
                incident_phi_deg=float(incidence["azimuth_deg"]),
                polarization_kind=str(incidence["polarization"]).lower(),
                h_nm=4.0,
                modal_h_nm=4.0,
            )
        _emit_marker(marker_callback, "profile_ready", profile_id=profile.profile_id)
        watchdog = v3_7_watchdog_policy(resolved_payload)
        _emit_marker(
            marker_callback,
            "watchdog_ready",
            absolute_terminate_memory_bytes=V3_7_ABSOLUTE_HARD_BYTES,
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
        ):
            raise ValueError(
                "V3-7 requires an injected recovery_runner(setup, layout, snapshot, "
                "run_dir, producer)"
            )
        if v5_h4_setup_only:
            if (
                selected_mode_packet_manifest is None
                or selected_mode_packet_identity is None
                or selected_mode_packet_manifest_sha256 is None
            ):
                raise ValueError("V5 h4 setup-only requires the shared packet identity")
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
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        modal_cfg = deepcopy(cfg)
        _emit_marker(marker_callback, "config_ready")
        producer["_stage_callback"] = marker_callback
        _emit_marker(marker_callback, "setup_begin")
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
        if v5_h4_setup_only:
            result = run_v5_h4_exact_side_setup_only(
                setup,
                layout,
                comm=comm,
                marker_callback=marker_callback,
                sampled_column_contract=v5_sampled_column_contract,
                streaming_w_batch_size=v5_streaming_w_batch_size,
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
                setup_release = release_frozen_m10_objects(setup, None, comm)
                object_ledger["objects"]["setup"]["destroyed"] = True
                object_ledger["objects"]["setup"]["completed"] = True
                if v5_h4_setup_only:
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
                                and result.get("status") == "setup_only_completed"
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
            if v5_h4_setup_only and result is not None:
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
                }
                for name in ("exact_side_action", "exact_side_factors"):
                    object_ledger["objects"][name].update(
                        {
                            "created": bool(side_actions),
                            "completed": result.get("status") == "setup_only_completed",
                            "destroyed": cleanup_pass,
                            "status": "measured" if cleanup_pass else "incomplete",
                            "lifecycle_pass": cleanup_pass,
                            "details": details,
                        }
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
    parser.add_argument("--v5-h4-blr-side-component", action="store_true")
    parser.add_argument("--selected-mode-packet-manifest")
    parser.add_argument("--selected-mode-packet-identity")
    parser.add_argument("--selected-mode-packet-manifest-sha256")
    parser.add_argument("--input", required=True, dest="input_path")
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
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
                bool(args.v5_h4_blr_side_component),
            )
        )
        > 1
    ):
        parser.error(
            "candidate routes, --v5-h4-setup-only, and --v5-h4-blr-side-component are mutually exclusive"
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
            v5_h4_blr_side_only=args.v5_h4_blr_side_component,
            selected_mode_packet_manifest=args.selected_mode_packet_manifest,
            selected_mode_packet_identity=(
                args.selected_mode_packet_identity
                if args.v5_h4_setup_only or args.v5_h4_blr_side_component
                else None
            ),
            selected_mode_packet_manifest_sha256=(
                args.selected_mode_packet_manifest_sha256
                if args.v5_h4_setup_only or args.v5_h4_blr_side_component
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
        if args.v5_h4_setup_only or args.v5_h4_blr_side_component:
            specification = load_and_resolve(args.input_path)
            payload = specification.as_jsonable()
            from benchmarks.task039_v4_h4_hybrid_direct import (
                validate_v4_h4_specification,
            )

            validate_v4_h4_specification(specification)
            if specification.method.get("kind") != "hybrid_iterative":
                raise ValueError("V5 h4 component requires hybrid_iterative")
            packet_identity = json.loads(
                Path(args.selected_mode_packet_identity).read_text(encoding="utf-8")
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
                if args.candidate_b_only
                or args.candidate_c_only
                or args.candidate_e_side_only
                or args.v5_h4_setup_only
                or args.v5_h4_blr_side_component
                else run_v3_7_recovery_runner
            ),
            candidate_b_only=args.candidate_b_only,
            candidate_c_only=args.candidate_c_only,
            candidate_d_only=args.candidate_d_only,
            candidate_d_qualified=args.candidate_d_qualified,
            candidate_e_side_only=args.candidate_e_side_only,
            v5_h4_setup_only=args.v5_h4_setup_only,
            v5_h4_blr_side_only=args.v5_h4_blr_side_component,
            selected_mode_packet_manifest=(
                args.selected_mode_packet_manifest
                if args.v5_h4_setup_only or args.v5_h4_blr_side_component
                else None
            ),
            selected_mode_packet_identity=packet_identity,
            selected_mode_packet_manifest_sha256=(
                args.selected_mode_packet_manifest_sha256
                if args.v5_h4_setup_only or args.v5_h4_blr_side_component
                else None
            ),
            record_path=(
                Path(args.run_directory).resolve()
                / "numerical_output"
                / "v3_v7_diagnostic.json"
            ),
        )
    except Exception as exc:
        print(
            f"V3-7 worker failed before completion: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(_json_safe(result), ensure_ascii=False, sort_keys=True))
    return (
        0
        if result.get("status")
        in {"completed", "setup_only_completed", "component_completed"}
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
