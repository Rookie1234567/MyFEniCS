from __future__ import annotations

import argparse
import csv
import hashlib
import math
import json
import os
import secrets
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    effective_memory_limit,
    vmstat_swap_pages,
)
from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MPI_SIZES,
    task035c_p6_h10_preflight_authority_gate,
    valid_hex_digest,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_FILE_SHA256,
    TASK035D_LOCAL_H_PLAN_NAME,
    task035d_case097_combined_hp_plan_authority_gate,
    task035d_case097_combined_hp_solver_gate,
    task035d_case097_hp_factorial_bridge_plan_authority_gate,
    task035d_case097_hp_factorial_bridge_solver_gate,
    task035d_case097_left_grating_top_plan_authority_gate,
    task035d_case097_left_grating_top_solver_gate,
    task035d_case097_local_h_plan_authority_gate,
    task035d_case097_local_h_solver_gate,
    task035d_case097_plan_authority_gate,
    task035d_case097_sidewall_guard_plan_authority_gate,
    task035d_case097_sidewall_guard_solver_gate,
    task035d_case097_t30_solver_gate,
)
from benchmarks.task035d_selective_face_case097_gates import (
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
    task035d_case097_selective_face_plan_authority_gate,
    task035d_case097_selective_face_solver_gate,
)
from benchmarks.task035d_selective_face_dwr_checker import (
    load_selective_face_coarse_endpoint,
    task035d_selective_face_dwr_report_gate,
)
from benchmarks.task035d_selective_face_snapshot_gate import (
    task035d_selective_face_coarse_snapshot_gate,
)
from benchmarks.task035d_nested_p_snapshot_gate import (
    task035d_coarse_snapshot_artifact_gate,
)
from benchmarks.task035d_nested_p_dwr_checker import (
    task035d_nested_p_dwr_report_gate,
)
from benchmarks.watchdog_process_control import (
    terminate_process_tree,
    worker_process_group_popen_kwargs,
)
from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _historical_peak_upper_bound,
    _read_progress_events,
    _sample,
    _source_provenance,
    _stage_peaks,
)
from src.solvers.common_3d_utils import _write_progress_event


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "cases" / "091" / "task033_full3d"
)
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
GIB = 1024**3
LONG_MAX_IT = 1_000_000
LONG_TIMEOUT = 604800.0
_PARENT_LAUNCH_TOKEN_ENV = "MYFENICS_WATCHDOG_PARENT_TOKEN"
TASK035D_LOCAL_H_CANDIDATES = {
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
}
TASK035D_NESTED_P_PHASES = {
    "coarse-snapshot",
    "enriched-evaluate",
}
TASK035D_SELECTIVE_FACE_PHASES = {
    "coarse-snapshot",
    "enriched-evaluate",
}
TASK037_E2_B4_ITERATIONS = (0, 20, 100, 200)


def _task037_e2_b4_admission(args: argparse.Namespace) -> dict[str, Any]:
    """Centralize the frozen research-only B4 carrier admission."""

    conflicts = {
        "f0_vector_observer": bool(args.task037_f0_vector_observer),
        "e0_gate": bool(args.task037_e0_matrix_free_dtn_gate),
        "e1_gate": bool(args.task037_e1_modal_basis_gate),
        "canonical_export": bool(args.task037_canonical_vector_export),
        "f1_oracle": args.task037_f1_direct_trace_oracle is not None,
        "f3_full": bool(args.task037_f3_full),
        "f5b": bool(args.task037_f5b_released_profile),
        "m4_optimized_schwarz": bool(args.task037_m4_optimized_schwarz),
        "m4_b2_long_full": bool(args.task037_m4_b2_long_full),
        "m0_lifecycle": bool(args.task037_m0_lifecycle_audit),
        "task035d": bool(args.task035d_case097_gate),
        "task035d_nested": args.task035d_nested_p_dwr_phase is not None,
        "task035d_selective_face": (
            args.task035d_selective_face_dwr_phase is not None
        ),
        "task034": bool(args.task034_p4_h3_added_point),
    }
    checks = {
        "identity": (
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size == 8
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend
            == "assembly_time_static_condensed"
        ),
        "task035c_p6_h10": bool(args.task035c_p6_h10_gate),
        "preflight_authority": args.task035c_p6_preflight_authority is not None,
        "preflight_sha": valid_hex_digest(args.task035c_p6_preflight_sha256, 64),
        "verified_clean_sha": valid_hex_digest(args.verified_clean_sha, 40),
        "no_swap": not args.allow_swap,
        "screen_200": args.task037_f3_screen == 200,
        "m2c_never_materialized": bool(args.task037_m2c_never_materialized),
        "m3a_overlap_partition_flag_disabled": not bool(
            args.task037_m3a_overlap0125_partition
        ),
        "m4_p2_auxiliary": bool(args.task037_m4_p2_auxiliary),
        "m4_factor_free_slab": bool(args.task037_m4_factor_free_slab),
        "factor_free_local_steps": args.task037_m4_factor_free_local_steps == 4,
        "no_conflicting_research_flag": not any(conflicts.values()),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "iterations": list(TASK037_E2_B4_ITERATIONS),
    }


def _task037_e2_modal_capacity_admission(args: argparse.Namespace) -> dict[str, Any]:
    """Reuse the frozen B4 identity admission for the live capacity gate."""

    return _task037_e2_b4_admission(args)


def _read_int_or_max(path: Path) -> tuple[int | None, str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, "unreadable"
    if text == "max":
        return None, "unbounded"
    try:
        return int(text), "finite"
    except ValueError:
        return None, "unreadable"


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _host_available_bytes() -> int | None:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("MemAvailable:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _resource_snapshot() -> dict[str, Any]:
    cgroup = cgroup_snapshot()
    memory = effective_memory_limit()
    swap = vmstat_swap_pages()
    memory_max = cgroup.get("memory_limit_bytes")
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cgroup_path": cgroup.get("path"),
        "cgroup_is_dedicated_job_authority": cgroup.get("dedicated_job_cgroup", False),
        "cgroup_memory_max_bytes": memory_max,
        "cgroup_memory_max_state": (
            "finite" if isinstance(memory_max, int) else "unbounded_or_unreadable"
        ),
        "cgroup_swap_max_bytes": None,
        "cgroup_swap_max_state": "not_used_as_limit",
        "cgroup_memory_current_bytes": cgroup.get("memory_current_bytes"),
        "cgroup_swap_current_bytes": cgroup.get("swap_current_bytes"),
        "host_available_bytes": memory.get("mem_available_bytes"),
        "wsl_total_bytes": memory.get("mem_total_bytes"),
        "task034_effective_limit": memory,
        "wsl_vm_global_swap_diagnostic": swap,
    }


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_number_le(value: Any, limit: float) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= float(limit)
    )


def _task035d_selective_face_controlled_negative(
    payload: Any,
    *,
    report_sha256: str | None,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    negative_statuses = {
        "controlled_negative_cross_trace_galerkin_failure",
        "controlled_negative_enriched_primal_residual",
        "controlled_negative_unit_adjoint_exception",
        "controlled_negative_unit_adjoint_incomplete",
        "selective_face_cross_trace_live_dwr_fail",
    }
    status = payload.get("status")
    identity = payload.get("identity_checks")
    endpoint_authorities = payload.get("endpoint_identity_authorities")
    endpoint_fields = {
        "source_sha",
        "mesh_sha256",
        "normalized_config_sha256",
        "ordered_modes_sha256",
        "cell_interior_degree_sha256",
        "incident_projections_sha256",
        "auxiliary_coordinate_scales_sha256",
    }
    coarse_endpoint = (
        endpoint_authorities.get("coarse")
        if isinstance(endpoint_authorities, Mapping)
        else None
    )
    enriched_endpoint = (
        endpoint_authorities.get("enriched")
        if isinstance(endpoint_authorities, Mapping)
        else None
    )
    transfer = payload.get("root_transfer")
    galerkin = payload.get("galerkin_audit")
    common_evidence = bool(
        valid_hex_digest(report_sha256, 64)
        and payload.get("schema_version")
        == "task035d.selective-face-cross-trace-dwr.v1"
        and payload.get("pass") is False
        and payload.get("controlled_negative") is True
        and payload.get("ordinary_default_changed") is False
        and status in negative_statuses
        and isinstance(identity, Mapping)
        and set(identity)
        == {
            "same_source_sha",
            "same_mesh",
            "same_normalized_config",
            "same_ordered_modes",
            "same_cell_interior_degree_map",
            "same_incident_projections",
            "same_auxiliary_coordinate_scales",
        }
        and all(value is True for value in identity.values())
        and isinstance(endpoint_authorities, Mapping)
        and endpoint_authorities.get("schema_version")
        == "task035d.selective-face-endpoint-identities.v1"
        and isinstance(coarse_endpoint, Mapping)
        and isinstance(enriched_endpoint, Mapping)
        and set(coarse_endpoint) == endpoint_fields
        and set(enriched_endpoint) == endpoint_fields
        and coarse_endpoint == enriched_endpoint
        and valid_hex_digest(coarse_endpoint.get("source_sha"), 40)
        and all(
            valid_hex_digest(coarse_endpoint.get(name), 64)
            for name in endpoint_fields - {"source_sha"}
        )
        and isinstance(transfer, Mapping)
        and transfer.get("schema_version")
        in {
            "task035d.selective-face-physical-root-transfer.v1",
            "task035d.selective-face-physical-root-transfer.v2",
        }
        and transfer.get("pass") is True
        and isinstance(galerkin, Mapping)
        and galerkin.get("schema_version")
        == "task035d.selective-face-cross-trace-galerkin-audit.v1"
    )
    if not common_evidence:
        return False
    if status == "controlled_negative_cross_trace_galerkin_failure":
        return bool(
            payload.get("failure_stage") == "cross_trace_galerkin_before_adjoints"
            and galerkin.get("pass") is False
        )
    if status == "controlled_negative_enriched_primal_residual":
        residual = payload.get("enriched_primal_residual_gate")
        return bool(
            payload.get("failure_stage") == "enriched_primal_residual_before_adjoints"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is False
        )
    if status == "controlled_negative_unit_adjoint_exception":
        residual = payload.get("enriched_primal_residual_gate")
        errors = payload.get("errors")
        completed = payload.get("completed_unit_channel_pairing_count")
        return bool(
            payload.get("failure_stage") == "unit_channel_adjoint_basis"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is True
            and isinstance(errors, list)
            and bool(errors)
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("rank"), int)
                and isinstance(row.get("exception_type"), str)
                and isinstance(row.get("message"), str)
                for row in errors
            )
            and isinstance(completed, int)
            and not isinstance(completed, bool)
            and 0 <= completed <= 12
        )
    if status == "controlled_negative_unit_adjoint_incomplete":
        residual = payload.get("enriched_primal_residual_gate")
        basis = payload.get("unit_channel_adjoint_basis")
        observed = payload.get("observed_unit_pairing_labels")
        expected = payload.get("expected_unit_pairing_labels")
        return bool(
            payload.get("failure_stage") == "unit_channel_adjoint_basis_gate"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is True
            and isinstance(basis, Mapping)
            and basis.get("schema_version")
            == "task035d.actual-dtn-unit-channel-adjoint-basis.v2"
            and isinstance(observed, list)
            and isinstance(expected, list)
            and len(expected) == 12
        )
    primal = payload.get("primal_endpoints")
    basis = payload.get("unit_channel_adjoint_basis")
    goals = payload.get("goal_dwr")
    marking = payload.get("selected_face_multigoal_marking")
    return bool(
        status == "selective_face_cross_trace_live_dwr_fail"
        and payload.get("canonical") is False
        and payload.get("production_qualified") is False
        and payload.get("same_trace_only") is False
        and payload.get("actual_cross_trace_primal_prolongation_used") is True
        and isinstance(payload.get("coarse_snapshot"), Mapping)
        and isinstance(payload.get("enriched_candidate"), Mapping)
        and galerkin.get("pass") is True
        and isinstance(primal, Mapping)
        and isinstance(primal.get("coarse_residual_gate"), Mapping)
        and primal["coarse_residual_gate"].get("pass") is True
        and isinstance(primal.get("enriched_residual_gate"), Mapping)
        and primal["enriched_residual_gate"].get("pass") is True
        and isinstance(payload.get("significant_channel_authority"), Mapping)
        and isinstance(basis, Mapping)
        and basis.get("schema_version")
        == "task035d.actual-dtn-unit-channel-adjoint-basis.v2"
        and basis.get("pass") is True
        and isinstance(goals, Mapping)
        and goals.get("schema_version") == "task035d.selective-face-live-36-goal-dwr.v1"
        and goals.get("pass") is False
        and goals.get("requested_real_goal_count") == 36
        and isinstance(goals.get("goals"), Mapping)
        and len(goals["goals"]) == 36
        and isinstance(marking, Mapping)
        and marking.get("face_count") == 10
        and isinstance(marking.get("ranked_faces"), list)
        and len(marking["ranked_faces"]) == 10
        and isinstance(payload.get("formal_boundary"), Mapping)
    )


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _task037_canonical_identity(namespace: str, values: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(values, dtype="<c16"))
    descriptor = json.dumps(
        [namespace, list(array.shape), array.dtype.str], separators=(",", ":")
    ).encode("utf-8")
    return {
        "namespace": namespace,
        "shape": list(array.shape),
        "dtype": array.dtype.str,
        "sha256": hashlib.sha256(
            descriptor + b"\0" + array.tobytes(order="C")
        ).hexdigest(),
    }


def _task037_collect_owned_vector(petsc_vec: Any, comm: Any) -> np.ndarray | None:
    start, end = map(int, petsc_vec.getOwnershipRange())
    local = np.asarray(petsc_vec.getArray(readonly=True), dtype="<c16").copy()
    packets = comm.gather((start, end, local), root=0)
    if comm.rank:
        return
    ordered = sorted(packets, key=lambda packet: int(packet[0]))
    cursor = 0
    pieces: list[np.ndarray] = []
    for packet_start, packet_end, packet_values in ordered:
        packet_start, packet_end = map(int, (packet_start, packet_end))
        if packet_start != cursor or packet_end <= packet_start:
            raise RuntimeError("Task37 owned-vector ranges are not contiguous.")
        pieces.append(np.asarray(packet_values, dtype="<c16"))
        cursor = packet_end
    if cursor != int(petsc_vec.getSize()):
        raise RuntimeError("Task37 owned-vector ranges do not cover global size.")
    return np.concatenate(pieces)


def _task037_write_canonical_solution_artifacts(
    run_dir: Path,
    role: str,
    *,
    field: Any,
    mesh_data: Any,
    floquet_data: Any,
    summary: dict[str, Any],
    linear_system: dict[str, Any],
    dtn_result: dict[str, Any],
) -> None:
    from mpi4py import MPI
    from petsc4py import PETSc

    from benchmarks.canonical_vector_artifacts import (
        MANIFEST_SCHEMA,
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_active_trace_packets,
        extract_canonical_full_fe_packets,
    )

    comm = mesh_data.mesh.comm
    started = time.perf_counter()
    _write_progress_event(
        run_dir,
        comm,
        stage="task037_canonical_vector_export",
        status="begin",
        extra={"role": role, "schema_version": MANIFEST_SCHEMA},
    )
    context = dtn_result["canonical_vector_context"]
    condensed = context["assembly_time_system"]
    function_space = field.function_space
    x = linear_system["x"]
    start, end = map(int, x.getOwnershipRange())
    active_rows = int(condensed.active_rows)
    local_n = max(0, min(end, active_rows) - start)
    active_is = PETSc.IS().createStride(
        local_n,
        first=start,
        step=1,
        comm=x.getComm(),
    )
    active_vec = x.getSubVector(active_is)
    try:
        active_packets, active_audit = extract_canonical_active_trace_packets(
            condensed,
            function_space,
            floquet_data,
            active_vec,
        )
    finally:
        x.restoreSubVector(active_is, active_vec)
        active_is.destroy()
    full_packets, full_audit = extract_canonical_full_fe_packets(
        function_space,
        field.x.petsc_vec,
        floquet_data,
    )
    raw_prefix = "task037" if role == "f0" else f"task037_{role}"
    exports: dict[str, dict[str, Any]] = {}
    for packet_role, packets, audit in (
        ("active_trace", active_packets, active_audit),
        ("full_fe", full_packets, full_audit),
    ):
        shard_path = run_dir / (
            f"{raw_prefix}_{packet_role}_canonical_rank{comm.rank:04d}.jsonl"
        )
        shard = write_canonical_packet_shard(shard_path, packets)
        shard.update(
            {
                "rank": int(comm.rank),
                "local_duplicate_count": int(audit["local_duplicate_count"]),
                "extractor_audit": audit,
            }
        )
        by_rank = comm.gather(shard, root=0)
        if comm.rank == 0:
            by_rank = sorted(by_rank, key=lambda item: int(item["rank"]))
            manifest = canonical_shard_manifest(
                role=packet_role,
                mpi_size=comm.size,
                shard_metadata=by_rank,
                extractor_audit={
                    "by_rank": [item["extractor_audit"] for item in by_rank]
                },
            )
            manifest_path = run_dir / (
                f"{raw_prefix}_{packet_role}_canonical_manifest.json"
            )
            manifest_sha256 = write_canonical_manifest(manifest_path, manifest)
            exports[packet_role] = {
                "manifest": _path_from_root(manifest_path),
                "manifest_sha256": manifest_sha256,
                "global_summed_packet_count": manifest["global_summed_packet_count"],
                "schema_version": MANIFEST_SCHEMA,
            }
        exports = comm.bcast(exports if comm.rank == 0 else None, root=0)
    elapsed_seconds = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
    if comm.rank == 0:
        summary["task037_canonical_vector_export"] = {
            "status": "completed",
            "schema_version": MANIFEST_SCHEMA,
            "roles": exports,
            "canonical_export_elapsed_seconds": elapsed_seconds,
        }
    _write_progress_event(
        run_dir,
        comm,
        stage="task037_canonical_vector_export",
        status="end",
        extra={
            "role": role,
            "schema_version": MANIFEST_SCHEMA,
            "manifests": exports,
            "canonical_export_elapsed_seconds": elapsed_seconds,
        },
    )


def _task037_f0_solution_observer(
    run_dir: Path, role: str = "f0", canonical_export: bool = False
):
    raw_prefix = "task037" if role == "f0" else f"task037_{role}"
    namespace = f"task037.{role}"
    identity_key = f"task037_{role}_vector_identity"

    def observe(
        *,
        field: Any,
        mesh_data: Any,
        config: Any,
        floquet_data: Any,
        summary: dict[str, Any],
        linear_system: dict[str, Any],
        dtn_result: dict[str, Any],
    ) -> None:
        comm = mesh_data.mesh.comm
        active_rows = int(dtn_result["solver_info"]["num_active_trace_dofs"])
        system_values = _task037_collect_owned_vector(linear_system["x"], comm)
        recovered_values = _task037_collect_owned_vector(field.x.petsc_vec, comm)
        if canonical_export:
            _task037_write_canonical_solution_artifacts(
                run_dir,
                role,
                field=field,
                mesh_data=mesh_data,
                floquet_data=floquet_data,
                summary=summary,
                linear_system=linear_system,
                dtn_result=dtn_result,
            )
        if comm.rank != 0:
            return
        active_values = system_values[:active_rows]
        np.save(run_dir / f"{raw_prefix}_active_trace_vector.npy", active_values)
        np.save(
            run_dir / f"{raw_prefix}_recovered_full_fe_vector.npy", recovered_values
        )
        summary[identity_key] = {
            "active_trace": {
                **_task037_canonical_identity(
                    f"{namespace}.active_trace",
                    active_values,
                ),
                "source": "linear_system.x prefix; raw=ignored run_dir",
            },
            "recovered_full_fe": {
                **_task037_canonical_identity(
                    f"{namespace}.recovered_full_fe",
                    recovered_values,
                ),
                "source": "field.x.petsc_vec ownership order; raw=ignored run_dir",
            },
        }

    return observe


def _task037_f1_direct_trace_oracle(trace_path: Path, trace_sha256: str):
    from src.solvers.condensed_dtn import (
        combine_petsc_augmented_solution,
        condensed_rhs,
        create_matrix_free_condensed_operator,
        extract_petsc_condensed_blocks,
        full_augmented_relative_residual,
        recover_petsc_auxiliary,
    )
    from src.solvers.dtn_port_3d import (
        Stage4ExternalLinearSolverSnapshot,
        _linear_residual,
    )

    def solve(request):
        trace = np.load(trace_path)
        if _sha256(trace_path) != trace_sha256 or trace.shape != (request.n_fe,):
            raise ValueError("direct trace oracle identity or shape failed")
        blocks = extract_petsc_condensed_blocks(
            request.A, request.b, n_fe=request.n_fe, n_aux=request.n_aux
        )
        u_fe = blocks.require_f().createVecRight()
        start, end = map(int, u_fe.getOwnershipRange())
        u_fe.getArray()[:] = trace[start:end]
        operator, _ = create_matrix_free_condensed_operator(blocks)
        rhs = condensed_rhs(blocks)
        condensed_residual = _linear_residual(operator, rhs, u_fe)[
            "linear_system_relative_residual"
        ]
        u_aux = recover_petsc_auxiliary(blocks, u_fe)
        target = request.A.createVecRight()
        combine_petsc_augmented_solution(blocks, u_fe, u_aux, target)
        full_residual = full_augmented_relative_residual(blocks, u_fe, u_aux)
        operator.destroy()
        rhs.destroy()
        u_aux.destroy()
        u_fe.destroy()
        blocks.destroy()
        return Stage4ExternalLinearSolverSnapshot(
            x=target,
            converged_reason=1,
            iterations=0,
            reported_relative_residual=condensed_residual,
            condensed_true_residual=condensed_residual,
            full_augmented_true_residual=full_residual,
            ksp_type="direct_vector_oracle",
            pc_type="none",
            residual_limit=1.0e-9,
            no_global_factor=True,
        )

    return solve


def _task037_f3_iterations(args: argparse.Namespace) -> int | None:
    if args.task037_m4_b2_long_full:
        return LONG_MAX_IT
    return 3000 if args.task037_f3_full else args.task037_f3_screen


def _task037_m3a_status(
    args: argparse.Namespace, qualification: Mapping[str, Any]
) -> str | None:
    if not args.task037_m3a_overlap0125_partition:
        return None
    phase = "full" if args.task037_f3_full else "screen"
    result = "pass" if qualification["pass"] else "not_pass"
    return f"task037_m3a_overlap0125_partition_{phase}_{result}"


def _task037_m4_factor_free_status(
    args: argparse.Namespace, qualification: Mapping[str, Any]
) -> str | None:
    if not args.task037_m4_factor_free_slab:
        return None
    phase = "full" if args.task037_f3_full else f"{args.task037_f3_screen}_screen"
    result = "pass" if qualification["pass"] else "not_pass"
    return (
        "task037_m4_p2_factor_free_slab_"
        f"steps{args.task037_m4_factor_free_local_steps}_{phase}_{result}"
    )


def _task037_m4_b2_long_full_status(
    args: argparse.Namespace, qualification: Mapping[str, Any]
) -> str | None:
    if not args.task037_m4_b2_long_full:
        return None
    result = "pass" if qualification["pass"] else "not_pass"
    return f"task037_m4_b2_factor_free_mpi1_long_full_{result}"


def _task037_m4_optimized_schwarz_status(
    args: argparse.Namespace, qualification: Mapping[str, Any]
) -> str | None:
    if not args.task037_m4_optimized_schwarz:
        return None
    phase = "full" if args.task037_f3_full else f"{args.task037_f3_screen}_screen"
    result = "pass" if qualification["pass"] else "not_pass"
    return f"task037_m4_p2_factor_free_slab_ras_steps4_{phase}_{result}"


def _task037_f3_assembled_fgmres_port(
    run_dir: Path,
    screen_iterations: int,
    *,
    solver_profile: str = "assembled",
    lifecycle_enabled: bool = False,
    never_materialized: bool = False,
    p2_auxiliary: bool = False,
    factor_free_slab: bool = False,
    factor_free_local_steps: int = 2,
    optimized_schwarz: bool = False,
    overlap0125_partition: bool = False,
):
    from src.solvers.static_condensed_iterative import (
        solve_assembled_static_condensed_fgmres,
        solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres,
        solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres,
        solve_never_materialized_overlap0125_partition_fgmres,
        solve_never_materialized_p2_auxiliary_fgmres,
        solve_never_materialized_static_condensed_fgmres,
    )

    def solve(request):
        request_operator = request.operator if never_materialized else request.A
        comm = request_operator.getComm().tompi4py()
        history_path = run_dir / "task037_f3_residual_history.jsonl"

        def observe(iteration, reported, condensed):
            if comm.rank == 0:
                payload = {
                    "iteration": int(iteration),
                    "reported_relative_residual": float(reported),
                    "condensed_true_residual": float(condensed),
                }
                with history_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

        def observe_lifecycle(event, payload):
            ledgers_by_rank = comm.gather(payload, root=0)
            _write_progress_event(
                run_dir,
                comm,
                stage=f"m0_{event}",
                status="end",
                extra={
                    "task037_m0_lifecycle": True,
                    "m0_event": event,
                    "task037_m0_rank_ledgers_by_rank": (
                        ledgers_by_rank if comm.rank == 0 else None
                    ),
                    **payload,
                },
            )

        if optimized_schwarz:
            snapshot, audit = (
                solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres(
                    request,
                    screen_iterations=screen_iterations,
                    residual_observer=observe,
                    lifecycle_observer=(
                        observe_lifecycle if lifecycle_enabled else None
                    ),
                )
            )
        elif factor_free_slab:
            snapshot, audit = (
                solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres(
                    request,
                    screen_iterations=screen_iterations,
                    local_krylov_steps=factor_free_local_steps,
                    residual_observer=observe,
                    lifecycle_observer=(
                        observe_lifecycle if lifecycle_enabled else None
                    ),
                )
            )
        elif p2_auxiliary:
            snapshot, audit = solve_never_materialized_p2_auxiliary_fgmres(
                request,
                screen_iterations=screen_iterations,
                residual_observer=observe,
                lifecycle_observer=(observe_lifecycle if lifecycle_enabled else None),
            )
        elif overlap0125_partition:
            snapshot, audit = solve_never_materialized_overlap0125_partition_fgmres(
                request,
                screen_iterations=screen_iterations,
                residual_observer=observe,
                lifecycle_observer=(observe_lifecycle if lifecycle_enabled else None),
            )
        elif never_materialized:
            snapshot, audit = solve_never_materialized_static_condensed_fgmres(
                request,
                screen_iterations=screen_iterations,
                residual_observer=observe,
                lifecycle_observer=(observe_lifecycle if lifecycle_enabled else None),
            )
        else:
            snapshot, audit = solve_assembled_static_condensed_fgmres(
                request,
                screen_iterations=screen_iterations,
                residual_observer=observe,
                solver_profile=solver_profile,
                release_assembled_matrix=request.release_assembled_matrix,
                lifecycle_observer=(observe_lifecycle if lifecycle_enabled else None),
            )
        audit["task037_m4_b2_long_full"] = screen_iterations == LONG_MAX_IT
        if comm.rank == 0:
            (run_dir / "task037_f3_core_audit.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return snapshot

    return solve


def _task037_f3_screen_gate(
    audit: Mapping[str, Any],
    expected_screen_iterations: int,
    observed_wall_seconds: float | None,
    expected_factor_free_steps: int | None = None,
    expected_factor_free_variant: str | None = None,
) -> dict[str, bool]:
    m3_profile = (
        audit.get("solver_profile")
        == "never_materialized_owner_local_overlap0125_partition"
    )
    m4_factor_free_profile = (
        audit.get("solver_profile")
        == "never_materialized_p2_factor_free_slab_auxiliary"
    )
    m4_optimized_schwarz_profile = (
        audit.get("solver_profile")
        == "never_materialized_p2_factor_free_slab_ras_auxiliary"
    )
    m4_profile = audit.get("solver_profile") == "never_materialized_p2_auxiliary"
    try:
        candidate = audit["candidate"]
        final = audit["final"]
        history = [(int(row[0]), float(row[1])) for row in audit["reported_history"]]
        samples = [
            (int(row[0]), float(row[1])) for row in audit["condensed_true_samples"]
        ]
        reported = dict(history)
        condensed_history = dict(samples)
        pairs = [(reported[iteration], value) for iteration, value in samples]
        history_by_iteration = dict(history)
        initial_reported, initial_condensed = history[0], samples[0]
        final_values = tuple(
            float(final[name])
            for name in (
                "reported_relative_residual",
                "condensed_true_residual",
                "full_augmented_true_residual",
            )
        )
        reason, iterations = int(final["converged_reason"]), int(final["iterations"])
        final_history_value = history_by_iteration[iterations]
        comparison_iteration = (
            max(0, iterations - 40)
            if expected_screen_iterations in (100, 200)
            else iterations
        )
        comparison_history_value = history_by_iteration[comparison_iteration]
        coarse = audit["coarse"]
        smoother = audit["smoother_diagnostics"]
        partition = audit["partition_audit"]
        inventory = audit["no_global_factor_inventory"]
        coarse_dimension = int(coarse["dimension"])
        factor_free_steps = expected_factor_free_steps
        if m4_factor_free_profile or m4_optimized_schwarz_profile:
            expected_candidate = {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": expected_screen_iterations,
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "local_krylov_steps": factor_free_steps,
                "local_inner_preconditioner": "none",
                "outer_requires_fgmres": True,
                "p2_auxiliary_correction": True,
                "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
                "fine_schur_action_kind": ("borrowed_p6_static_local_schur_action"),
                "wave_coarse_post_smooth": False,
            }
            if m4_optimized_schwarz_profile:
                expected_candidate.update(
                    {
                        "variant": "ras",
                        "correction_partition": "one_hot_ras",
                        "interface_shift_mode": "shared_rows_only",
                    }
                )
            counts = (
                int(audit["operator_apply_count"]),
                int(coarse["apply_count"]),
                int(smoother["apply_count"]),
            )
            patch = smoother["factor_free_slab_patch"]
            p2_setup = audit["p2_auxiliary_audit"]
            weight_error = partition.get("partition_weight_sum_error")
            weight_min = partition.get("partition_weight_min")
            weight_max = partition.get("partition_weight_max")
            variant_gate = (
                not m4_optimized_schwarz_profile
                and expected_factor_free_variant is None
                and patch.get("partition_weighted_additive_schwarz") is True
            ) or (
                m4_optimized_schwarz_profile
                and expected_factor_free_variant == "ras"
                and partition.get("variant") == "ras"
                and partition.get("correction_partition") == "one_hot_ras"
                and partition.get("ras_core_sum_error") is not None
                and float(partition["ras_core_sum_error"]) <= 1.0e-12
                and partition.get("interface_row_count", 0) > 0
                and partition.get("interface_shift_mode") == "shared_rows_only"
                and partition.get("interface_shift_nonzero_rows")
                == partition.get("interface_row_count")
                and partition.get("noninterface_shift_nonzero_rows") == 0
                and patch.get("variant") == "ras"
                and patch.get("correction_partition") == "one_hot_ras"
                and patch.get("interface_shift_mode") == "shared_rows_only"
                and patch.get("interface_shift_nonzero_rows")
                == patch.get("interface_row_count")
                and patch.get("interface_row_count", 0) > 0
                and patch.get("noninterface_shift_nonzero_rows") == 0
                and patch.get("partition_weighted_additive_schwarz") is False
            )
            partition_or_factor_gate = (
                partition.get("p6_slab_matrix_materialized") is False
                and partition.get("p6_slab_matrix_count") == 0
                and partition.get("p6_factor_count") == 0
                and partition.get("p6_factor_nnz") == 0
                and partition.get("num_slabs") == 16
                and partition.get("overlap_fraction") == 0.125
                and partition.get("interpolation") == "partition"
                and factor_free_steps in (2, 4)
                and partition.get("local_krylov_steps") == factor_free_steps
                and partition.get("local_inner_preconditioner") == "none"
                and partition.get("outer_requires_fgmres") is True
                and partition.get("global_A_materialized_by_pc") is False
                and variant_gate
                and patch.get("local_krylov_steps") == factor_free_steps
                and patch.get("local_inner_preconditioner") == "none"
                and patch.get("outer_requires_fgmres") is True
                and patch.get("p6_slab_matrix_materialized") is False
                and patch.get("p6_slab_matrix_count") == 0
                and patch.get("p6_factor_count") == 0
                and patch.get("p6_factor_nnz") == 0
                and patch.get("global_A_materialized_by_pc") is False
                and patch.get("expected_action_calls")
                == factor_free_steps * 16 * int(patch.get("apply_count", 0))
                and isinstance(weight_error, (int, float))
                and math.isfinite(float(weight_error))
                and float(weight_error) <= 1.0e-12
                and isinstance(weight_min, (int, float))
                and isinstance(weight_max, (int, float))
                and 0.0 < float(weight_min) <= float(weight_max) <= 1.0
            )
            no_global_factor = (
                audit.get("global_A_materialized") is False
                and audit.get("global_F_materialized") is False
                and inventory.get("full_p6_global_direct_factor_count") == 0
                and inventory.get("global_schur_matrix_materialized") is False
                and inventory.get("p6_factor_count") == 0
                and inventory.get("p6_factor_nnz") == 0
                and inventory.get("p2_distributed_mumps_factor_count") == 1
                and inventory.get("wave_coarse_dense_lu_count") == 1
                and smoother.get("profile")
                == (
                    "never_materialized_p2_factor_free_slab_ras_auxiliary"
                    if m4_optimized_schwarz_profile
                    else "never_materialized_p2_factor_free_slab_auxiliary"
                )
                and smoother.get("fine_operator_kind")
                == "borrowed_p6_condensed_dtn_action"
                and p2_setup.get("profile")
                == (
                    "never_materialized_p2_factor_free_slab_ras_auxiliary"
                    if m4_optimized_schwarz_profile
                    else "never_materialized_p2_factor_free_slab_auxiliary"
                )
                and p2_setup.get("fine_operator_kind")
                == "borrowed_p6_condensed_dtn_action"
                and p2_setup.get("fine_schur_action_kind")
                == "borrowed_p6_static_local_schur_action"
                and smoother.get("global_p6_matrix_materialized") is False
                and smoother.get("global_p6_transfer_materialized") is False
                and smoother.get("p2_factor_count") == 1
                and smoother.get("p2_factor_solver_type") == "mumps"
                and smoother.get("p2_matrix_materialized") is True
                and smoother.get("p2_unshifted_matrix_retained") is False
            )
        elif m4_profile:
            expected_candidate = {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": expected_screen_iterations,
                "p6_smoothing": "not_used",
                "p2_auxiliary_correction": True,
                "p2_absorption_shift": 0.1,
                "p2_diagonal_patch_omega": 0.6,
                "wave_coarse_post_smooth": False,
            }
            counts = (
                int(audit["operator_apply_count"]),
                int(coarse["apply_count"]),
                int(smoother["apply_count"]),
            )
            partition_or_factor_gate = (
                partition.get("p6_slab_matrix_materialized") is False
                and partition.get("p6_slab_matrix_count") == 0
                and partition.get("p6_factor_count") == 0
            )
            no_global_factor = (
                inventory.get("full_p6_global_direct_factor_count") == 0
                and inventory.get("global_schur_matrix_materialized") is False
                and inventory.get("p2_distributed_mumps_factor_count") == 1
                and inventory.get("wave_coarse_dense_lu_count") == 1
                and smoother.get("p2_matrix_materialized") is True
                and smoother.get("p2_unshifted_matrix_retained") is False
            )
        elif m3_profile:
            expected_candidate = {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": expected_screen_iterations,
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "absorption_shift": 0.1,
            }
            counts = (
                int(audit["operator_apply_count"]),
                int(coarse["apply_count"]),
                int(smoother["one_level_apply_count"]),
            )
            local_types = tuple(smoother["local_solver_types"])
            weight_error = partition.get("partition_weight_sum_error")
            weight_min = partition.get("partition_weight_min")
            weight_max = partition.get("partition_weight_max")
            partition_or_factor_gate = (
                partition.get("matrix_materialized") is False
                and partition.get("coverage_pass") is True
                and partition.get("num_slabs") == 16
                and partition.get("overlap_fraction") == 0.125
                and partition.get("interpolation") == "partition"
                and smoother.get("interpolation") == "partition"
                and isinstance(weight_error, (int, float))
                and math.isfinite(float(weight_error))
                and float(weight_error) <= 1.0e-12
                and isinstance(weight_min, (int, float))
                and isinstance(weight_max, (int, float))
                and 0.0 < float(weight_min) <= float(weight_max) <= 1.0
                and smoother["assembly_order"] == "two_color"
                and smoother["smoother_iterations"] == 2
                and smoother["smoother_ksp_type"] == "gmres"
                and smoother["factor_only_storage"] is True
                and bool(local_types)
                and all(kind == "ilu" for kind in local_types)
                and int(smoother["global_stored_factor_nnz"]) < 103336560
            )
            no_global_factor = (
                audit.get("global_A_materialized") is False
                and audit.get("global_F_materialized") is False
                and inventory.get("global_direct_factor_count") == 0
                and inventory.get("global_schur_matrix_materialized") is False
            )
        else:
            expected_candidate = {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": expected_screen_iterations,
                "num_slabs": 16,
                "overlap_fraction": 0.25,
                "absorption_shift": 0.1,
            }
            counts = (
                int(audit["operator_apply_count"]),
                int(coarse["apply_count"]),
                int(smoother["one_level_apply_count"]),
            )
            local_types = tuple(smoother["local_solver_types"])
            coverage = partition["coverage_pass"] is True
            factor_only = smoother["factor_only_storage"] is True
            partition_or_factor_gate = (
                coverage
                and factor_only
                and bool(local_types)
                and all(kind == "ilu" for kind in local_types)
            )
            no_global_factor = (
                inventory["global_direct_factor_count"] == 0
                and inventory["global_schur_matrix_materialized"] is False
            )
        if expected_screen_iterations == 200:
            target = 1.0e-6
            predicted_iterations = iterations if final_values[0] <= target else math.inf
            if target < final_values[0] < comparison_history_value:
                log_rate = math.log(final_values[0] / comparison_history_value) / (
                    iterations - comparison_iteration
                )
                predicted_iterations = math.ceil(
                    iterations + math.log(target / final_values[0]) / log_rate
                )
            predicted_wall_seconds = (
                float(observed_wall_seconds) * predicted_iterations / iterations
            )
        if (
            m3_profile or m4_factor_free_profile or m4_optimized_schwarz_profile
        ) and expected_screen_iterations == 20:
            if {0, 10, 20}.issubset(reported):
                m3a_screen_decline = (
                    reported[20] < reported[10] < reported[0]
                    and condensed_history[20]
                    < condensed_history[10]
                    < condensed_history[0]
                )
            else:
                m3a_screen_decline = (
                    reason > 0
                    and iterations < expected_screen_iterations
                    and reported.get(iterations, final_values[0]) < reported[0]
                )
        else:
            m3a_screen_decline = True
    except (KeyError, TypeError, ValueError, IndexError):
        return {"core_audit": False}
    tiny = np.finfo(float).tiny
    history_values = tuple(value for _, value in history)
    sample_values = tuple(value for _, value in samples)
    finite = all(
        math.isfinite(value)
        for value in (*history_values, *sample_values, *final_values)
    )
    same_order = all(
        max(abs(left), abs(right)) <= 10.0 * max(min(abs(left), abs(right)), tiny)
        for left, right in pairs
    )
    final_order = max(final_values) <= 10.0 * max(min(final_values), tiny)
    scale = finite and initial_reported[0] == initial_condensed[0] == 0
    scale &= max(map(abs, history_values)) <= 10.0 * abs(initial_reported[1])
    scale &= max(map(abs, sample_values)) <= 10.0 * abs(initial_condensed[1])
    scale &= max(map(abs, final_values)) <= 10.0
    return {
        "candidate": candidate == expected_candidate,
        "finite_and_scale": scale,
        "pairing_and_order": same_order and final_order,
        "reason_iteration": (reason < 0 and iterations == expected_screen_iterations)
        or (reason > 0 and all(value <= 1.0e-6 for value in final_values)),
        "apply_counts": (all(value > 0 for value in counts) and coarse_dimension == 75),
        "partition_and_ilu": partition_or_factor_gate,
        "no_global_factor": no_global_factor,
        "screen_100": expected_screen_iterations != 100
        or (
            final_values[1] <= 3.0e-1
            and final_values[2] <= 3.0e-1
            and final_history_value < comparison_history_value
        ),
        "screen_200": expected_screen_iterations != 200
        or (
            final_values[2] <= 5.0e-2
            and predicted_iterations <= 3000
            and predicted_wall_seconds <= 7200
        ),
        **({"m3a_screen_decline": m3a_screen_decline} if m3_profile else {}),
        **(
            {"m4_factor_free_screen_decline": m3a_screen_decline}
            if m4_factor_free_profile
            else {}
        ),
        **(
            {"m4_optimized_schwarz_screen_decline": m3a_screen_decline}
            if m4_optimized_schwarz_profile
            else {}
        ),
    }


def _full3d_config(args: argparse.Namespace):
    from src.common.config_3d import target_stage4_config

    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    full_solve = args.run_kind == "full-solve"
    factorization_only = args.run_kind == "factorization-only"
    return replace(
        cfg,
        polarization_kind=args.polarization_kind,
        custom_polarization=None,
        stage4_full3d_assembly_backend=(args.stage4_full3d_assembly_backend),
        stage4_variable_p_cell_degree_plan=(
            None
            if args.stage4_variable_p_cell_degree_plan is None
            else str(args.stage4_variable_p_cell_degree_plan)
        ),
        stage4_local_h_refinement_plan=(
            None
            if args.stage4_local_h_refinement_plan is None
            else str(args.stage4_local_h_refinement_plan)
        ),
        direct_release_base_after_augmentation=bool(args.task035d_case097_gate),
        direct_release_solver_before_postprocess=bool(args.task035d_case097_gate),
        petsc_direct_solver_profile=args.profile,
        petsc_extra_options={
            **cfg.petsc_extra_options,
            **({"mat_mumps_icntl_14": 100} if args.task035d_case097_gate else {}),
        },
        matrix_diagnostics_assemble_only=args.run_kind == "assembly-only",
        matrix_diagnostics_factorization_only=factorization_only,
        full3d_reference_export=full_solve,
        full3d_reference_plane_z=REFERENCE_PLANES_NM if full_solve else (),
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )


def _worker_launch_contract(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "degree": int(args.degree),
        "h_nm": float(args.h_nm),
        "polarization_kind": str(args.polarization_kind),
        "run_kind": str(args.run_kind),
        "mpi_size": int(args.mpi_size),
        "profile": str(args.profile),
        "run_dir": str(Path(args.run_dir).resolve()),
        "stage4_full3d_assembly_backend": str(args.stage4_full3d_assembly_backend),
        "task037_f0_vector_observer": bool(args.task037_f0_vector_observer),
        "task037_e0_matrix_free_dtn_gate": bool(args.task037_e0_matrix_free_dtn_gate),
        "task037_e1_modal_basis_gate": bool(args.task037_e1_modal_basis_gate),
        "task037_e2_b4_snapshot_carrier": bool(
            args.task037_e2_b4_snapshot_carrier
        ),
        "task037_e2_modal_capacity_gate": bool(
            args.task037_e2_modal_capacity_gate
        ),
        "task037_f1_direct_trace_oracle": (
            None
            if args.task037_f1_direct_trace_oracle is None
            else str(Path(args.task037_f1_direct_trace_oracle).resolve())
        ),
        "task037_f1_direct_trace_sha256": args.task037_f1_direct_trace_sha256,
        "task037_f3_screen": args.task037_f3_screen,
        "task037_f3_full": bool(args.task037_f3_full),
        "task037_f5b_released_profile": bool(args.task037_f5b_released_profile),
        "task037_m2c_never_materialized": bool(args.task037_m2c_never_materialized),
        "task037_m3a_overlap0125_partition": bool(
            args.task037_m3a_overlap0125_partition
        ),
        "task037_m4_p2_auxiliary": bool(args.task037_m4_p2_auxiliary),
        "task037_m4_factor_free_slab": bool(args.task037_m4_factor_free_slab),
        "task037_m4_b2_long_full": bool(args.task037_m4_b2_long_full),
        "task037_m4_optimized_schwarz": bool(args.task037_m4_optimized_schwarz),
        "task037_m4_factor_free_local_steps": int(
            args.task037_m4_factor_free_local_steps
        ),
        "task037_canonical_vector_export": bool(args.task037_canonical_vector_export),
        "task037_m0_lifecycle_audit": bool(args.task037_m0_lifecycle_audit),
        "task035d_case097_gate": bool(args.task035d_case097_gate),
        "task035d_candidate_id": str(args.task035d_candidate_id),
        "task035d_nested_p_dwr_phase": args.task035d_nested_p_dwr_phase,
        "task035d_selective_face_dwr_phase": (args.task035d_selective_face_dwr_phase),
        "task035d_plan_authority_sha256": (args.task035d_plan_authority_sha256),
        "task035d_significant_channel_authority_sha256": (
            args.task035d_significant_channel_authority_sha256
        ),
        "task035d_coarse_snapshot_manifest_sha256": (
            args.task035d_coarse_snapshot_manifest_sha256
        ),
        "task035d_selective_face_coarse_manifest_sha256": (
            args.task035d_selective_face_coarse_manifest_sha256
        ),
        "verified_clean_sha": args.verified_clean_sha,
    }


def _linux_process_identity(pid: int) -> dict[str, int]:
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        suffix = stat[stat.rindex(")") + 2 :].split()
        return {
            "pid": int(pid),
            "parent_pid": int(suffix[1]),
            "start_time_ticks": int(suffix[19]),
        }
    except (IndexError, OSError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Linux process identity is unreadable for pid {pid}: {exc}"
        ) from exc


def _linux_process_ancestor_pids(pid: int) -> set[int]:
    ancestors: set[int] = set()
    cursor = int(pid)
    for _ in range(128):
        identity = _linux_process_identity(cursor)
        parent = identity["parent_pid"]
        if parent <= 0 or parent == cursor:
            break
        if parent in ancestors:
            raise RuntimeError("Linux process ancestry contains a cycle")
        ancestors.add(parent)
        cursor = parent
    return ancestors


def _validate_worker_parent_launch(args: argparse.Namespace) -> None:
    descriptor_path = args.parent_launch_descriptor
    expected_sha = args.parent_launch_descriptor_sha256
    token = os.environ.get(_PARENT_LAUNCH_TOKEN_ENV)
    if (
        descriptor_path is None
        or not valid_hex_digest(expected_sha, 64)
        or not isinstance(token, str)
        or len(token) < 32
    ):
        raise SystemExit(
            "--worker is internal to the resource watchdog and requires "
            "one process-bound parent launch lease."
        )
    descriptor_path = descriptor_path.resolve()
    run_dir = Path(args.run_dir).resolve()
    if (
        descriptor_path.parent != run_dir
        or descriptor_path.name != "parent_launch_descriptor.json"
        or _sha256(descriptor_path) != expected_sha
    ):
        raise SystemExit("worker parent-launch descriptor identity failed.")
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"worker parent-launch descriptor is unreadable: {exc}"
        ) from exc
    token_sha256 = hashlib.sha256(token.encode("ascii")).hexdigest()
    parent_process = (
        payload.get("parent_process") if isinstance(payload, Mapping) else None
    )
    try:
        parent_identity = (
            _linux_process_identity(int(parent_process["pid"]))
            if isinstance(parent_process, Mapping)
            else {}
        )
        ancestors = _linux_process_ancestor_pids(os.getpid())
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"worker parent-launch process lease failed: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "task033.watchdog-parent-launch.v1"
        or payload.get("token_sha256") != token_sha256
        or payload.get("worker_contract") != _worker_launch_contract(args)
        or not isinstance(parent_process, Mapping)
        or parent_process.get("role") != "resource_watchdog_parent"
        or parent_process.get("pid") not in ancestors
        or parent_identity.get("start_time_ticks")
        != parent_process.get("start_time_ticks")
    ):
        raise SystemExit("worker parent-launch descriptor contract failed.")


def _revalidate_task035d_worker_inputs(args: argparse.Namespace) -> None:
    if not (
        args.task035d_case097_gate
        or _task037_f3_iterations(args) is not None
        or args.task037_e0_matrix_free_dtn_gate
        or args.task037_e1_modal_basis_gate
        or args.task037_e2_b4_snapshot_carrier
        or args.task037_e2_modal_capacity_gate
    ):
        return
    if args.task035d_case097_gate:
        _validate_task035d_case097_plan(args)
        _validate_task035d_nested_p_inputs(args)
        _validate_task035d_selective_face_inputs(args)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    if head != args.verified_clean_sha or status:
        raise SystemExit(
            "Task035d/Task37 F3/E0/E1 worker source identity is not the clean "
            "parent-qualified commit."
        )


def _task037_e2_b4_snapshot_port(run_dir: Path, source_sha: str):
    from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort
    from src.solvers.static_condensed_iterative import (
        solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres,
    )
    from src.solvers.static_modal_coarse_gate import (
        OwnerLocalBasis,
        save_owner_local_basis_shard,
    )

    def solve(request):
        comm = request.operator.getComm().tompi4py()
        residual_vectors: dict[int, Any] = {}
        samples: dict[int, dict[str, Any]] = {}

        def observe_true_residual(iteration, residual, rhs_norm):
            iteration = int(iteration)
            if iteration not in TASK037_E2_B4_ITERATIONS:
                return
            local = np.asarray(residual.getArray(readonly=True), dtype=np.complex128)
            copied = residual.duplicate()
            residual.copy(copied)
            residual_vectors[iteration] = copied
            samples[iteration] = {
                "global_rows": int(residual.getSize()),
                "ownership": [int(value) for value in residual.getOwnershipRange()],
                "local_finite": bool(np.all(np.isfinite(local))),
                "relative_true_residual": float(
                    residual.norm() / max(float(rhs_norm), np.finfo(float).tiny)
                ),
            }

        snapshot, core_audit = (
            solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres(
                request,
                screen_iterations=200,
                local_krylov_steps=4,
                true_residual_vector_observer=observe_true_residual,
            )
        )
        expected_iterations = tuple(TASK037_E2_B4_ITERATIONS)
        if tuple(sorted(residual_vectors)) != expected_iterations:
            raise RuntimeError(
                "TASK037_E2_B4_TRUE_RESIDUAL_SAMPLES_INCOMPLETE"
            )
        vectors = tuple(residual_vectors[index] for index in expected_iterations)
        basis = OwnerLocalBasis.from_vectors(
            vectors,
            label="task037_e2_b4_true_residual",
            research_opt_in=True,
        )
        try:
            shard_dir = run_dir / "e2_b4_snapshot"
            manifest = save_owner_local_basis_shard(
                basis,
                shard_dir,
                source_sha=source_sha,
                prefix="true_residual",
                research_opt_in=True,
            )
        finally:
            basis.destroy()
        samples_by_rank = comm.gather(samples, root=0)
        manifest_path = shard_dir / "true_residual.manifest.json"
        gate_payload = None
        if comm.rank == 0:
            candidate = core_audit.get("candidate")
            candidate = candidate if isinstance(candidate, dict) else {}
            factor_inventory = core_audit.get("no_global_factor_inventory")
            factor_inventory = (
                factor_inventory if isinstance(factor_inventory, dict) else {}
            )
            core_samples = core_audit.get("condensed_true_samples")
            core_samples = core_samples if isinstance(core_samples, list) else []
            core_values = {
                int(item[0]): float(item[1])
                for item in core_samples
                if isinstance(item, (list, tuple)) and len(item) == 2
            }
            relative_values = {
                str(iteration): float(samples[iteration]["relative_true_residual"])
                for iteration in expected_iterations
            }
            checks = {
                "iterations_exact": tuple(sorted(samples)) == expected_iterations,
                "finite": all(
                    bool(samples_by_rank[rank][iteration]["local_finite"])
                    for rank in range(comm.size)
                    for iteration in expected_iterations
                ),
                "positive_rows": all(
                    int(samples[iteration]["global_rows"]) > 0
                    for iteration in expected_iterations
                ),
                "core_scalar_identity": all(
                    iteration in core_values
                    and abs(
                        relative_values[str(iteration)] - core_values[iteration]
                    )
                    <= 1.0e-12
                    for iteration in expected_iterations
                ),
                "solver_profile": (
                    core_audit.get("solver_profile")
                    == "never_materialized_p2_factor_free_slab_auxiliary"
                ),
                "restart": candidate.get("restart") == 90,
                "max_it": candidate.get("max_it") == 200,
                "local_krylov_steps": candidate.get("local_krylov_steps") == 4,
                "overlap_fraction": candidate.get("overlap_fraction") == 0.125,
                "partition": candidate.get("interpolation") == "partition",
                "global_A_materialized": (
                    core_audit.get("global_A_materialized") is False
                ),
                "global_F_materialized": (
                    core_audit.get("global_F_materialized") is False
                ),
                "p6_factor_count": factor_inventory.get("p6_factor_count") == 0,
                "p6_factor_nnz": factor_inventory.get("p6_factor_nnz") == 0,
                "manifest_source": manifest.get("source_sha") == source_sha,
                "manifest_global_rows": manifest.get("global_rows") == 51192,
                "manifest_column_count": manifest.get("column_count") == 4,
                "manifest_shard_count": len(manifest.get("shards", ())) == 8,
                "manifest_owner_local": manifest.get("owner_local") is True,
                "manifest_not_replicated": (
                    manifest.get("replicated_global_basis") is False
                ),
            }
            gate_payload = {
                "schema_version": "task037.e2.b4.true-residual-carrier.v1",
                "candidate": "B4_true_residual_snapshot_carrier",
                "source_sha": source_sha,
                "carrier_gate_pass": not [name for name, ok in checks.items() if not ok],
                "checks": checks,
                "iterations": list(expected_iterations),
                "true_residual_samples": [
                    {
                        "iteration": iteration,
                        "relative_true_residual": relative_values[str(iteration)],
                        "core_relative_true_residual": core_values.get(iteration),
                        "global_rows": int(samples[iteration]["global_rows"]),
                        "owner_ranges_by_rank": [
                            samples_by_rank[rank][iteration]["ownership"]
                            for rank in range(comm.size)
                        ],
                    }
                    for iteration in expected_iterations
                ],
                "owner_local": True,
                "replicated_global_vector": False,
                "manifest": {
                    "path": _path_from_root(manifest_path),
                    "sha256": _sha256(manifest_path),
                    "bytes": manifest_path.stat().st_size,
                    "source_sha": manifest["source_sha"],
                    "global_rows": int(manifest["global_rows"]),
                    "column_count": int(manifest["column_count"]),
                    "owner_local": bool(manifest["owner_local"]),
                    "replicated_global_basis": bool(
                        manifest["replicated_global_basis"]
                    ),
                    "shard_count": len(manifest["shards"]),
                    "total_shard_bytes": sum(
                        int(entry["bytes"]) for entry in manifest["shards"]
                    ),
                },
                "config": {
                    "mpi_size": comm.size,
                    "screen_iterations": candidate.get("max_it"),
                    "restart": candidate.get("restart"),
                    "local_krylov_steps": candidate.get("local_krylov_steps"),
                    "overlap_fraction": candidate.get("overlap_fraction"),
                    "partition": candidate.get("interpolation"),
                    "global_A_materialized": core_audit.get(
                        "global_A_materialized"
                    ),
                    "global_F_materialized": core_audit.get(
                        "global_F_materialized"
                    ),
                },
                "solver_profile": core_audit.get("solver_profile"),
                "p6_factor_inventory": factor_inventory,
                "core_condensed_true_samples": [
                    [iteration, core_values.get(iteration)]
                    for iteration in expected_iterations
                ],
                "solver_convergence_gate": {
                    "pass": int(snapshot.converged_reason) > 0,
                    "converged_reason": int(snapshot.converged_reason),
                    "iterations": int(snapshot.iterations),
                    "independent_of_carrier_gate": True,
                },
            }
            (run_dir / "task037_e2_b4_snapshot_audit.json").write_text(
                json.dumps(gate_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "task037_f3_core_audit.json").write_text(
                json.dumps(core_audit, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            history_path = run_dir / "task037_f3_residual_history.jsonl"
            history = core_audit.get("reported_history", ())
            reported_values = {int(iteration): float(reported) for iteration, reported in history}
            with history_path.open("w", encoding="utf-8") as stream:
                for iteration in expected_iterations:
                    stream.write(
                        json.dumps(
                            {
                                "iteration": iteration,
                                "reported_relative_residual": reported_values.get(
                                    iteration
                                ),
                                "condensed_true_residual": core_values.get(
                                    iteration
                                ),
                            }
                        )
                        + "\n"
                    )
        gate_payload = comm.bcast(gate_payload, root=0)
        if not gate_payload["carrier_gate_pass"]:
            raise RuntimeError("TASK037_E2_B4_TRUE_RESIDUAL_CARRIER_GATE_FAILED")
        return snapshot

    return Stage4NeverMaterializedLinearSolverPort(solve)


def _task037_e2_capacity_port(run_dir: Path, source_sha: str):
    from mpi4py import MPI
    from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort
    from src.solvers.static_modal_capacity_oracle import run_e2_capacity_oracle
    from src.solvers.static_modal_coarse_gate import run_e1_modal_basis_gate

    def solve(request):
        comm = request.b.getComm().tompi4py()
        started = time.perf_counter()
        _write_progress_event(
            run_dir,
            comm,
            stage="task037_e1_modal_basis_generation",
            status="begin",
            extra={"research_only": True, "e2_capacity": True},
        )

        def live_capacity(z_m, y_m, a6_operator):
            capacity_started = time.perf_counter()
            _write_progress_event(
                run_dir,
                comm,
                stage="task037_e2_capacity_oracle",
                status="begin",
                extra={"research_only": True},
            )
            audit = run_e2_capacity_oracle(
                request,
                z_m,
                y_m,
                a6_operator,
                run_dir=run_dir,
                source_sha=source_sha,
                research_opt_in=True,
            )
            elapsed = float(
                comm.allreduce(time.perf_counter() - capacity_started, op=MPI.MAX)
            )
            _write_progress_event(
                run_dir,
                comm,
                stage="task037_e2_capacity_oracle",
                status="end",
                extra={
                    "collective_max_wall_seconds": elapsed,
                    "capacity_gate_pass": bool(audit["capacity_gate_pass"]),
                    "classification": audit["classification"],
                    "research_only": True,
                },
            )

        snapshot = run_e1_modal_basis_gate(
            request,
            run_dir=run_dir,
            source_sha=source_sha,
            research_opt_in=True,
            e2_live_callback=live_capacity,
        )
        elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
        _write_progress_event(
            run_dir,
            comm,
            stage="task037_e1_modal_basis_generation",
            status="end",
            extra={
                "collective_max_wall_seconds": elapsed,
                "e2_capacity": True,
                "research_only": True,
            },
        )
        return snapshot

    return Stage4NeverMaterializedLinearSolverPort(solve)


def _worker(args: argparse.Namespace) -> int:
    e0_gate = bool(getattr(args, "task037_e0_matrix_free_dtn_gate", False))
    e1_gate = bool(getattr(args, "task037_e1_modal_basis_gate", False))
    e2_gate = bool(getattr(args, "task037_e2_b4_snapshot_carrier", False))
    e2_capacity_gate = bool(
        getattr(args, "task037_e2_modal_capacity_gate", False)
    )
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    solution_observer = (
        _task037_f0_solution_observer(
            args.run_dir,
            role=("f5b_full" if args.task037_f5b_released_profile else "f3_full"),
            canonical_export=args.task037_canonical_vector_export,
        )
        if args.task037_f3_full
        else _task037_f0_solution_observer(
            args.run_dir,
            canonical_export=args.task037_canonical_vector_export,
        )
        if args.task037_f0_vector_observer
        else None
    )
    linear_solver_port = None
    if e2_gate:
        linear_solver_port = _task037_e2_b4_snapshot_port(
            Path(args.run_dir),
            args.verified_clean_sha,
        )
    elif e2_capacity_gate:
        linear_solver_port = _task037_e2_capacity_port(
            Path(args.run_dir),
            args.verified_clean_sha,
        )
    elif e1_gate:
        from mpi4py import MPI
        from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort
        from src.solvers.static_modal_coarse_gate import run_e1_modal_basis_gate

        def e1_callback(request):
            started = time.perf_counter()
            comm = request.b.getComm().tompi4py()
            _write_progress_event(
                args.run_dir,
                comm,
                stage="task037_e1_modal_basis_generation",
                status="begin",
                extra={"research_only": True},
            )
            snapshot = run_e1_modal_basis_gate(
                request,
                run_dir=args.run_dir,
                source_sha=args.verified_clean_sha,
                research_opt_in=True,
            )
            elapsed = float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))
            _write_progress_event(
                args.run_dir,
                comm,
                stage="task037_e1_modal_basis_generation",
                status="end",
                extra={
                    "collective_max_wall_seconds": elapsed,
                    "research_only": True,
                },
            )
            return snapshot

        linear_solver_port = Stage4NeverMaterializedLinearSolverPort(e1_callback)
    elif e0_gate:
        from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort

        def e0_sentinel(_request):
            raise RuntimeError("MATRIX_FREE_DTN_COMPONENT_SENTINEL_INVOKED")

        linear_solver_port = Stage4NeverMaterializedLinearSolverPort(e0_sentinel)
    elif args.task037_f3_full or args.task037_f3_screen is not None:
        linear_solver_callback = _task037_f3_assembled_fgmres_port(
            args.run_dir,
            _task037_f3_iterations(args),
            solver_profile=(
                "assembled_setup_then_static_local_schur_matrix_free_solve"
                if args.task037_f5b_released_profile
                else "assembled"
            ),
            lifecycle_enabled=args.task037_m0_lifecycle_audit,
            never_materialized=args.task037_m2c_never_materialized,
            p2_auxiliary=args.task037_m4_p2_auxiliary,
            factor_free_slab=args.task037_m4_factor_free_slab,
            factor_free_local_steps=args.task037_m4_factor_free_local_steps,
            optimized_schwarz=args.task037_m4_optimized_schwarz,
            overlap0125_partition=args.task037_m3a_overlap0125_partition,
        )
        if args.task037_m2c_never_materialized:
            from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort

            linear_solver_port = Stage4NeverMaterializedLinearSolverPort(
                linear_solver_callback
            )
        else:
            linear_solver_port = linear_solver_callback
    elif args.task037_f1_direct_trace_oracle is not None:
        linear_solver_port = _task037_f1_direct_trace_oracle(
            args.task037_f1_direct_trace_oracle,
            args.task037_f1_direct_trace_sha256,
        )
    observer = None
    retain_local_schur = False
    if args.task035d_nested_p_dwr_phase is not None:
        from src.adaptivity.variable_p_nested_dwr import (
            build_variable_p_nested_coarse_snapshot_observer,
            build_variable_p_nested_enriched_evaluator_observer,
        )

        common = {
            "candidate_id": args.task035d_candidate_id,
            "expected_plan_sha256": (args.stage4_local_h_refinement_plan_sha256),
            "source_sha": args.verified_clean_sha,
            "significant_channel_authority_path": (
                args.task035d_significant_channel_authority
            ),
            "significant_channel_authority_sha256": (
                args.task035d_significant_channel_authority_sha256
            ),
        }
        if args.task035d_nested_p_dwr_phase == "coarse-snapshot":
            observer = build_variable_p_nested_coarse_snapshot_observer(
                artifact_directory=(args.run_dir / "nested_p_snapshot"),
                **common,
            )
        else:
            observer = build_variable_p_nested_enriched_evaluator_observer(
                coarse_manifest_path=(args.task035d_coarse_snapshot_manifest),
                coarse_manifest_sha256=(args.task035d_coarse_snapshot_manifest_sha256),
                artifact_path=(args.run_dir / "nested_p_dwr_report.json"),
                **common,
            )
        retain_local_schur = True
    elif args.task035d_selective_face_dwr_phase is not None:
        from src.adaptivity.variable_p_selective_face_dwr import (
            build_selective_face_coarse_snapshot_observer,
            build_selective_face_enriched_evaluator_observer,
        )

        common = {
            "candidate_id": args.task035d_candidate_id,
            "expected_plan_sha256": (args.stage4_local_h_refinement_plan_sha256),
            "source_sha": args.verified_clean_sha,
            "significant_channel_authority_path": (
                args.task035d_significant_channel_authority
            ),
            "significant_channel_authority_sha256": (
                args.task035d_significant_channel_authority_sha256
            ),
        }
        if args.task035d_selective_face_dwr_phase == "coarse-snapshot":
            observer = build_selective_face_coarse_snapshot_observer(
                artifact_directory=(args.run_dir / "selective_face_snapshot"),
                **common,
            )
        else:
            observer = build_selective_face_enriched_evaluator_observer(
                coarse_manifest_path=(args.task035d_selective_face_coarse_manifest),
                coarse_manifest_sha256=(
                    args.task035d_selective_face_coarse_manifest_sha256
                ),
                artifact_path=(args.run_dir / "selective_face_dwr_report.json"),
                **common,
            )
    run_stage4b_block_grating_3d_case(
        _full3d_config(args),
        args.run_dir,
        linear_solver_port=linear_solver_port,
        solution_observer=solution_observer,
        variable_p_live_observer=observer,
        variable_p_retain_local_schur_for_research=(retain_local_schur),
        static_retain_local_schur_for_matrix_free=(
            args.task037_f5b_released_profile
            or args.task037_m2c_never_materialized
            or e0_gate
            or e1_gate
            or e2_gate
            or e2_capacity_gate
        ),
        matrix_free_dtn=e0_gate or e1_gate or e2_capacity_gate,
        matrix_free_dtn_probe=e0_gate,
        canonical_vector_export=args.task037_canonical_vector_export,
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task33/34 p2/p3/p4 target full3D assembly calibration and "
            "controlled direct-reference watchdog."
        )
    )
    parser.add_argument("--degree", type=int, choices=(2, 3, 4, 6), required=True)
    parser.add_argument(
        "--h-nm",
        type=float,
        choices=(15.0, 10.0, 7.5, 5.0, 3.0, 2.0, 1.0),
        default=5.0,
    )
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p"),
        default="s",
    )
    parser.add_argument(
        "--run-kind",
        choices=("assembly-only", "factorization-only", "full-solve"),
        default="assembly-only",
    )
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument(
        "--profile",
        choices=("default", "mumps_ooc", "mumps_blr"),
        default="default",
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            "standard_full",
            "assembly_time_static_condensed",
            TASK035D_CASE097_BACKEND,
        ),
        default="standard_full",
    )
    parser.add_argument("--stage4-variable-p-cell-degree-plan", type=Path)
    parser.add_argument("--stage4-variable-p-cell-degree-plan-sha256")
    parser.add_argument("--stage4-local-h-refinement-plan", type=Path)
    parser.add_argument("--stage4-local-h-refinement-plan-sha256")
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the Task035c fixed-rectangular p6/h10 "
            "Full3D authority path. Ordinary p2/p3/p4 behavior is unchanged."
        ),
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument(
        "--task037-f0-vector-observer",
        action="store_true",
        help="Export only the current-source Case100 F0 vector identities.",
    )
    parser.add_argument(
        "--task037-e0-matrix-free-dtn-gate",
        action="store_true",
        help=(
            "Run the research-only Task037 E0 80-mode matrix-free DtN component gate."
        ),
    )
    parser.add_argument(
        "--task037-e1-modal-basis-gate",
        action="store_true",
        help="Run the research-only Task037 E1 M120 modal-basis component gate.",
    )
    parser.add_argument(
        "--task037-e2-b4-snapshot-carrier",
        action="store_true",
        help="Capture the research-only frozen B4 true-residual vector carrier.",
    )
    parser.add_argument(
        "--task037-e2-modal-capacity-gate",
        action="store_true",
        help="Run the research-only same-request E2 modal capacity oracle.",
    )
    parser.add_argument(
        "--task037-canonical-vector-export",
        action="store_true",
        help="Export owner-local reversible canonical vector packet shards.",
    )
    parser.add_argument("--task037-f1-direct-trace-oracle", type=Path)
    parser.add_argument("--task037-f1-direct-trace-sha256")
    parser.add_argument("--task037-f3-screen", type=int, choices=(20, 100, 200))
    parser.add_argument("--task037-f3-full", action="store_true")
    parser.add_argument("--task037-f5b-released-profile", action="store_true")
    parser.add_argument("--task037-m2c-never-materialized", action="store_true")
    parser.add_argument("--task037-m3a-overlap0125-partition", action="store_true")
    parser.add_argument("--task037-m4-p2-auxiliary", action="store_true")
    parser.add_argument("--task037-m4-factor-free-slab", action="store_true")
    parser.add_argument("--task037-m4-optimized-schwarz", action="store_true")
    parser.add_argument(
        "--task037-m4-factor-free-local-steps",
        type=int,
        choices=(2, 4),
        default=2,
    )
    parser.add_argument("--task037-m4-b2-long-full", action="store_true")
    parser.add_argument("--task037-m0-lifecycle-audit", action="store_true")
    parser.add_argument(
        "--task035d-case097-gate",
        action="store_true",
        help=(
            "Explicitly open one frozen Task035d Case097 variable-p or "
            "balanced local-h MPI8 candidate. This grants no physical "
            "accuracy credit."
        ),
    )
    parser.add_argument(
        "--task035d-candidate-id",
        choices=(
            "t30",
            "sidewall_z0_guard_v1",
            TASK035D_LOCAL_H_PLAN_NAME,
            TASK035D_COMBINED_HP_PLAN_NAME,
            TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
            TASK035D_SELECTIVE_FACE_PLAN_NAME,
        ),
        default="t30",
    )
    parser.add_argument("--task035d-plan-authority", type=Path)
    parser.add_argument("--task035d-plan-authority-sha256")
    parser.add_argument(
        "--task035d-nested-p-dwr-phase",
        choices=tuple(sorted(TASK035D_NESTED_P_PHASES)),
        help=(
            "Explicitly add the same-trace nested-p coarse snapshot or "
            "enriched DWR live observer to one qualified Case097 MPI8 run."
        ),
    )
    parser.add_argument(
        "--task035d-selective-face-dwr-phase",
        choices=tuple(sorted(TASK035D_SELECTIVE_FACE_PHASES)),
        help=(
            "Explicitly add the true cross-trace selective-face coarse "
            "snapshot or enriched DWR observer to one qualified MPI8 run."
        ),
    )
    parser.add_argument(
        "--task035d-significant-channel-authority",
        type=Path,
    )
    parser.add_argument(
        "--task035d-significant-channel-authority-sha256",
    )
    parser.add_argument(
        "--task035d-nested-p-pair-authority",
        type=Path,
    )
    parser.add_argument(
        "--task035d-nested-p-pair-authority-sha256",
    )
    parser.add_argument(
        "--task035d-coarse-snapshot-manifest",
        type=Path,
    )
    parser.add_argument(
        "--task035d-coarse-snapshot-manifest-sha256",
    )
    parser.add_argument(
        "--task035d-selective-face-coarse-manifest",
        type=Path,
    )
    parser.add_argument(
        "--task035d-selective-face-coarse-manifest-sha256",
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--allow-swap",
        action="store_true",
        help=(
            "Permit a full solve to use cgroup swap. The combined memory+swap "
            "authority remains bounded by --terminate-gib."
        ),
    )
    parser.add_argument(
        "--p3-gate-record",
        type=Path,
        help=(
            "Required for degree 4. Must prove a successful p3/h5 full solve "
            "with zero swap and memory authority below 10 GiB."
        ),
    )
    parser.add_argument(
        "--p4-trace-record",
        type=Path,
        help=(
            "Required for degree 4. Must be the passing MPI1/MPI4 p4 "
            "four-mode matched-trace aggregate."
        ),
    )
    parser.add_argument(
        "--task034-p4-h3-added-point",
        action="store_true",
        help=(
            "Explicit Task034 user-added p4/h3 path. It retains the same-h "
            "p3 full-solve and current-SHA p4 trace prerequisites, but uses "
            "the live Task034 warning threshold instead of Task033's fixed "
            "10 GiB p3 cap."
        ),
    )
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK033_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--parent-launch-descriptor", type=Path)
    parser.add_argument("--parent-launch-descriptor-sha256")
    args = parser.parse_args(argv)
    if args.task037_e2_b4_snapshot_carrier or args.task037_e2_modal_capacity_gate:
        capacity_mode = bool(args.task037_e2_modal_capacity_gate)
        admission = (
            _task037_e2_modal_capacity_admission(args)
            if capacity_mode
            else _task037_e2_b4_admission(args)
        )
        mutual_exclusion_failures = (
            ["b4_carrier_e0_e1_mutual_exclusion"]
            if capacity_mode
            and (
                args.task037_e2_b4_snapshot_carrier
                or args.task037_e0_matrix_free_dtn_gate
                or args.task037_e1_modal_basis_gate
            )
            else []
        )
        failures = admission["failures"] + mutual_exclusion_failures
        if failures:
            flag_name = (
                "--task037-e2-modal-capacity-gate"
                if capacity_mode
                else "--task037-e2-b4-snapshot-carrier"
            )
            parser.error(
                f"{flag_name} admission failed: " + ", ".join(failures)
            )
    if (args.task037_f1_direct_trace_oracle is None) != (
        args.task037_f1_direct_trace_sha256 is None
    ):
        parser.error(
            "--task037-f1-direct-trace-oracle and --task037-f1-direct-trace-sha256 "
            "must be provided together."
        )
    allowed_h_by_degree = {
        2: {5.0, 3.0, 2.0, 1.0},
        3: {10.0, 7.5, 5.0, 3.0, 2.0},
        4: {10.0, 7.5, 5.0, 3.0},
        6: {15.0, 10.0},
    }
    if args.h_nm not in allowed_h_by_degree[args.degree]:
        parser.error(
            f"Task034 p{args.degree}/h{args.h_nm:g} is outside the "
            "fixed-geometry candidate matrix."
        )
    if args.task034_p4_h3_added_point and not (
        args.degree == 4 and math.isclose(args.h_nm, 3.0)
    ):
        parser.error("--task034-p4-h3-added-point is restricted to p4/h3.")
    selected_p6_gate_count = sum(
        (
            bool(args.task035c_p6_h10_gate),
            bool(args.task035d_case097_gate),
        )
    )
    if args.degree == 6 and selected_p6_gate_count != 1:
        parser.error(
            "p6 is fail-closed; select exactly one scoped Task035c or "
            "Task035d p6/h10 gate."
        )
    if args.degree != 6 and selected_p6_gate_count:
        parser.error("Task035c/Task035d p6 gates require --degree 6.")
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size in TASK035C_P6_H10_MPI_SIZES
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend in TASK035C_P6_H10_BACKENDS
            and not args.allow_swap
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to a clean-source, "
                "no-swap, default-profile fixed rectangular p6/h10 S-polarized "
                "full solve on MPI1/2/4/8 with standard_full or "
                "assembly_time_static_condensed and a hash-bound historical "
                "preflight authority."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
    ):
        parser.error(
            "Task035c p6 preflight authority arguments require --task035c-p6-h10-gate."
        )
    if args.task037_e0_matrix_free_dtn_gate:
        e0_conflicts = (
            args.task037_f0_vector_observer,
            args.task037_canonical_vector_export,
            args.task037_f1_direct_trace_oracle is not None,
            args.task037_f3_screen is not None,
            args.task037_f3_full,
            args.task037_f5b_released_profile,
            args.task037_m2c_never_materialized,
            args.task037_m3a_overlap0125_partition,
            args.task037_m4_p2_auxiliary,
            args.task037_m4_factor_free_slab,
            args.task037_m4_optimized_schwarz,
            args.task037_m4_b2_long_full,
            args.task037_m0_lifecycle_audit,
        )
        e0_scoped = bool(
            args.task035c_p6_h10_gate
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size in (1, 2, 4)
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and not args.allow_swap
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.task035d_case097_gate
            and not any(e0_conflicts)
        )
        if not e0_scoped:
            parser.error(
                "--task037-e0-matrix-free-dtn-gate is restricted to the "
                "Task035c p6/h10 S full-solve, assembly-time static-condensed "
                "MPI1/2/4 default-profile no-swap scope and is exclusive of "
                "all other Task037 research flags."
            )
    if args.task037_e1_modal_basis_gate:
        e1_conflicts = (
            args.task037_e0_matrix_free_dtn_gate,
            args.task037_f0_vector_observer,
            args.task037_canonical_vector_export,
            args.task037_f1_direct_trace_oracle is not None,
            args.task037_f3_screen is not None,
            args.task037_f3_full,
            args.task037_f5b_released_profile,
            args.task037_m2c_never_materialized,
            args.task037_m3a_overlap0125_partition,
            args.task037_m4_p2_auxiliary,
            args.task037_m4_factor_free_slab,
            args.task037_m4_optimized_schwarz,
            args.task037_m4_b2_long_full,
            args.task037_m0_lifecycle_audit,
            args.task035d_case097_gate,
            args.task034_p4_h3_added_point,
        )
        e1_scoped = bool(
            args.task035c_p6_h10_gate
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size == 8
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and not args.allow_swap
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not any(e1_conflicts)
        )
        if not e1_scoped:
            parser.error(
                "--task037-e1-modal-basis-gate is restricted to the "
                "Task035c p6/h10 S full-solve, assembly-time static-condensed "
                "MPI8 default-profile no-swap scope and is exclusive of all "
                "other Task037/Task035d research flags."
            )
    if (
        args.task037_f0_vector_observer
        or args.task037_f1_direct_trace_oracle is not None
        or args.task037_f3_screen is not None
        or args.task037_f3_full
    ) and not (
        args.task035c_p6_h10_gate
        and (
            args.mpi_size == 8
            or (
                args.task037_m3a_overlap0125_partition and args.mpi_size in (1, 2, 4, 8)
            )
            or (args.task037_m4_factor_free_slab and args.mpi_size in (1, 8))
        )
        and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    ):
        parser.error(
            "Task037 F0/F1/F3 options require the existing Task035c p6/h10 "
            "gate, full-solve, static backend, MPI8 for F0/F1 or MPI1/2/4/8 "
            "for M3a (MPI1/8 full for factor-free M4), "
            "and S scope."
        )
    canonical_f0_scope = (
        args.task037_f0_vector_observer
        and args.degree == 6
        and args.h_nm == 10.0
        and args.polarization_kind == "s"
        and args.run_kind == "full-solve"
        and args.mpi_size == 8
        and args.profile == "default"
        and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
        and args.task037_f1_direct_trace_oracle is None
        and args.task037_f3_screen is None
        and not args.task037_f3_full
        and not args.task037_f5b_released_profile
    )
    canonical_f5b_scope = (
        args.task037_f3_full
        and args.task037_f5b_released_profile
        and not args.task037_f0_vector_observer
        and args.task037_f1_direct_trace_oracle is None
        and args.task037_f3_screen is None
    )
    canonical_m3a_full_scope = (
        args.task037_f3_full
        and args.task037_m2c_never_materialized
        and args.task037_m3a_overlap0125_partition
        and args.task037_f3_screen is None
    )
    canonical_m4_factor_free_full_scope = (
        args.task037_f3_full
        and args.task037_m2c_never_materialized
        and args.task037_m4_p2_auxiliary
        and args.task037_m4_factor_free_slab
        and args.task037_f3_screen is None
    )
    if args.task037_canonical_vector_export and not (
        canonical_f0_scope
        or canonical_f5b_scope
        or canonical_m3a_full_scope
        or canonical_m4_factor_free_full_scope
    ):
        parser.error(
            "--task037-canonical-vector-export is restricted to the "
            "frozen F0 direct, F5b full, M3a full, or factor-free full profile."
        )
    if (args.task037_f3_screen is not None or args.task037_f3_full) and (
        args.task037_f3_full
        and args.task037_f3_screen is not None
        or args.task037_f0_vector_observer
        or args.task037_f1_direct_trace_oracle is not None
        or (
            not args.worker
            and not (
                args.poll_interval <= 0.25
                and args.warning_gib == 10.0
                and args.terminate_gib == 14.0
                and args.timeout_seconds
                == (
                    LONG_TIMEOUT
                    if args.task037_m4_b2_long_full
                    else 7200.0
                    if args.task037_f3_full
                    else 7200.0
                    if args.task037_e2_modal_capacity_gate
                    else 1800.0
                )
            )
        )
    ):
        parser.error(
            "Task037 F3 is exclusive of F0/F1 and requires fixed parent "
            "poll, warning, termination, and mode-specific timeout caps."
        )
    if args.task037_f5b_released_profile and not args.task037_f3_full:
        parser.error("--task037-f5b-released-profile requires --task037-f3-full.")
    if (
        args.task037_m2c_never_materialized
        and not args.task037_m3a_overlap0125_partition
        and not args.task037_m4_p2_auxiliary
        and not (
            args.task037_f3_screen == 20
            and not args.task037_f3_full
            and not args.task037_f5b_released_profile
            and not args.task037_f0_vector_observer
            and args.task037_f1_direct_trace_oracle is None
            and args.task035c_p6_h10_gate
            and args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.mpi_size == 8
            and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
            and not args.task037_m0_lifecycle_audit
        )
    ):
        parser.error(
            "--task037-m2c-never-materialized requires the existing p6/h10 "
            "MPI8 static-backend screen-20 path and is exclusive of F0/F1/F3-full/F5b."
        )
    if args.task037_m3a_overlap0125_partition and not (
        args.task037_m2c_never_materialized
        and (args.task037_f3_full or args.task037_f3_screen in (20, 100, 200))
        and not args.task037_f5b_released_profile
        and not args.task037_f0_vector_observer
        and args.task037_f1_direct_trace_oracle is None
        and not args.task037_m4_p2_auxiliary
        and not args.task037_m0_lifecycle_audit
        and args.mpi_size in (1, 2, 4, 8)
    ):
        parser.error(
            "--task037-m3a-overlap0125-partition requires the action-only "
            "Task037 screen/full path and is exclusive of M4/F5b/F0/F1."
        )
    if (
        args.task037_m4_p2_auxiliary
        and not args.task037_m4_factor_free_slab
        and not (
            args.task037_m2c_never_materialized
            and args.task037_f3_screen in (20, 100, 200)
            and not args.task037_f3_full
            and not args.task037_f5b_released_profile
            and not args.task037_m0_lifecycle_audit
        )
    ):
        parser.error(
            "--task037-m4-p2-auxiliary requires screen 20, 100, or 200 "
            "--task037-m2c-never-materialized path."
        )
    if args.task037_m4_factor_free_slab and not (
        args.task037_m4_p2_auxiliary
        and args.task037_m2c_never_materialized
        and not args.task037_f5b_released_profile
        and not args.task037_f0_vector_observer
        and args.task037_f1_direct_trace_oracle is None
        and not args.task037_m3a_overlap0125_partition
        and not args.task037_m0_lifecycle_audit
        and (
            (args.task037_f3_screen in (20, 100, 200) and args.mpi_size == 8)
            or (
                args.task037_f3_full
                and args.task037_f3_screen is None
                and args.mpi_size in (1, 8)
                and args.task037_canonical_vector_export
            )
        )
    ):
        parser.error(
            "--task037-m4-factor-free-slab requires the combined M2c/M4 p2 "
            "path, MPI8 screens 20/100/200, or canonical MPI1/8 full."
        )
    if args.task037_m4_factor_free_local_steps != 2 and not (
        args.task037_m4_factor_free_slab
    ):
        parser.error(
            "--task037-m4-factor-free-local-steps requires "
            "--task037-m4-factor-free-slab."
        )
    if args.task037_m4_optimized_schwarz and not (
        args.task037_m4_factor_free_slab
        and args.task037_m4_p2_auxiliary
        and args.task037_m2c_never_materialized
        and args.task037_m4_factor_free_local_steps == 4
        and not args.task037_f5b_released_profile
        and not args.task037_m3a_overlap0125_partition
        and not args.task037_f0_vector_observer
        and args.task037_f1_direct_trace_oracle is None
        and not args.task037_m0_lifecycle_audit
        and (
            (args.task037_f3_screen in (20, 100, 200) and args.mpi_size == 8)
            or (
                args.task037_f3_full
                and args.task037_f3_screen is None
                and args.mpi_size in (1, 8)
                and args.task037_canonical_vector_export
            )
        )
    ):
        parser.error(
            "--task037-m4-optimized-schwarz requires the fixed-four-step "
            "M2c/M4 factor-free screen or canonical full path."
        )
    if args.task037_m4_b2_long_full and not (
        args.mpi_size == 1
        and args.task037_f3_full
        and args.task037_m4_factor_free_slab
        and args.task037_m4_factor_free_local_steps == 2
        and args.task037_canonical_vector_export
        and not args.task037_m4_optimized_schwarz
        and (args.worker or args.timeout_seconds == LONG_TIMEOUT)
        and not args.allow_swap
    ):
        parser.error(
            "--task037-m4-b2-long-full requires the exact MPI1 canonical "
            "B2 factor-free full scope, fixed 604800-second timeout, and "
            "zero swap."
        )
    if args.task037_m0_lifecycle_audit and not (
        args.task037_f3_full and args.task037_f5b_released_profile
    ):
        parser.error(
            "--task037-m0-lifecycle-audit requires --task037-f3-full and "
            "--task037-f5b-released-profile."
        )
    if args.task035d_case097_gate:
        local_h_candidate = args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
        plan_scope = (
            args.stage4_variable_p_cell_degree_plan is None
            and args.stage4_variable_p_cell_degree_plan_sha256 is None
            and args.stage4_local_h_refinement_plan is not None
            and valid_hex_digest(
                args.stage4_local_h_refinement_plan_sha256,
                64,
            )
            if local_h_candidate
            else (
                args.stage4_variable_p_cell_degree_plan is not None
                and valid_hex_digest(
                    args.stage4_variable_p_cell_degree_plan_sha256,
                    64,
                )
                and args.stage4_local_h_refinement_plan is None
                and args.stage4_local_h_refinement_plan_sha256 is None
            )
        )
        scoped = bool(
            args.degree == 6
            and math.isclose(
                args.h_nm,
                15.0 if local_h_candidate else 10.0,
            )
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size == 8
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend == TASK035D_CASE097_BACKEND
            and not args.allow_swap
            and plan_scope
            and args.task035d_plan_authority is not None
            and valid_hex_digest(args.task035d_plan_authority_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.task035c_p6_h10_gate
            and args.task035c_p6_preflight_authority is None
            and args.task035c_p6_preflight_sha256 is None
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
        )
        if not scoped:
            parser.error(
                "--task035d-case097-gate is restricted to a clean-source, "
                "no-swap, default-profile fixed rectangular p6/h10 "
                "variable-p or p6/h15 balanced local-h S-polarized full "
                "solve on MPI8 using assembly_time_variable_p_condensed "
                "with one tracked, hash-bound candidate plan and MPI8 "
                "plan authority."
            )
        nested_phase = args.task035d_nested_p_dwr_phase
        selective_phase = args.task035d_selective_face_dwr_phase
        if nested_phase is not None and selective_phase is not None:
            parser.error(
                "Task035d same-trace nested-p and cross-trace "
                "selective-face observers are mutually exclusive."
            )
        if nested_phase is not None:
            expected_candidate = (
                TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
                if nested_phase == "coarse-snapshot"
                else TASK035D_LOCAL_H_PLAN_NAME
            )
            nested_scope = bool(
                args.task035d_candidate_id == expected_candidate
                and args.task035d_significant_channel_authority is not None
                and valid_hex_digest(
                    args.task035d_significant_channel_authority_sha256,
                    64,
                )
                and args.task035d_nested_p_pair_authority is not None
                and valid_hex_digest(
                    args.task035d_nested_p_pair_authority_sha256,
                    64,
                )
                and (
                    (
                        args.task035d_coarse_snapshot_manifest is None
                        and args.task035d_coarse_snapshot_manifest_sha256 is None
                    )
                    if nested_phase == "coarse-snapshot"
                    else (
                        args.task035d_coarse_snapshot_manifest is not None
                        and valid_hex_digest(
                            args.task035d_coarse_snapshot_manifest_sha256,
                            64,
                        )
                    )
                )
            )
            if not nested_scope:
                parser.error(
                    "Task035d nested-p DWR is restricted to the frozen "
                    "remote-p5-interior coarse B snapshot followed by the "
                    "all-p6-interior enriched A evaluation, with one "
                    "hash-bound A/B pair authority, significant-channel "
                    "authority, and coarse manifest."
                )
        elif selective_phase is not None:
            expected_candidate = (
                TASK035D_LOCAL_H_PLAN_NAME
                if selective_phase == "coarse-snapshot"
                else TASK035D_SELECTIVE_FACE_PLAN_NAME
            )
            selective_scope = bool(
                args.task035d_candidate_id == expected_candidate
                and args.task035d_significant_channel_authority is not None
                and valid_hex_digest(
                    args.task035d_significant_channel_authority_sha256,
                    64,
                )
                and args.task035d_nested_p_pair_authority is None
                and args.task035d_nested_p_pair_authority_sha256 is None
                and args.task035d_coarse_snapshot_manifest is None
                and args.task035d_coarse_snapshot_manifest_sha256 is None
                and (
                    (
                        args.task035d_selective_face_coarse_manifest is None
                        and (args.task035d_selective_face_coarse_manifest_sha256)
                        is None
                    )
                    if selective_phase == "coarse-snapshot"
                    else (
                        args.task035d_selective_face_coarse_manifest is not None
                        and valid_hex_digest(
                            (args.task035d_selective_face_coarse_manifest_sha256),
                            64,
                        )
                    )
                )
            )
            if not selective_scope:
                parser.error(
                    "Task035d selective-face DWR is restricted to the "
                    "frozen h15 p5-trace coarse snapshot followed by the "
                    "ten-face enriched candidate, with one hash-bound "
                    "significant-channel authority and coarse manifest."
                )
        elif any(
            value is not None
            for value in (
                args.task035d_significant_channel_authority,
                args.task035d_significant_channel_authority_sha256,
                args.task035d_nested_p_pair_authority,
                args.task035d_nested_p_pair_authority_sha256,
                args.task035d_coarse_snapshot_manifest,
                args.task035d_coarse_snapshot_manifest_sha256,
                args.task035d_selective_face_coarse_manifest,
                args.task035d_selective_face_coarse_manifest_sha256,
            )
        ):
            parser.error(
                "Task035d DWR authority arguments require one explicit "
                "nested-p or selective-face DWR phase."
            )
    elif (
        args.task035d_plan_authority is not None
        or args.task035d_plan_authority_sha256 is not None
        or args.stage4_variable_p_cell_degree_plan is not None
        or args.stage4_variable_p_cell_degree_plan_sha256 is not None
        or args.stage4_local_h_refinement_plan is not None
        or args.stage4_local_h_refinement_plan_sha256 is not None
        or args.stage4_full3d_assembly_backend == TASK035D_CASE097_BACKEND
        or args.task035d_candidate_id != "t30"
        or args.task035d_nested_p_dwr_phase is not None
        or args.task035d_selective_face_dwr_phase is not None
        or args.task035d_significant_channel_authority is not None
        or args.task035d_significant_channel_authority_sha256 is not None
        or args.task035d_nested_p_pair_authority is not None
        or args.task035d_nested_p_pair_authority_sha256 is not None
        or args.task035d_coarse_snapshot_manifest is not None
        or args.task035d_coarse_snapshot_manifest_sha256 is not None
        or args.task035d_selective_face_coarse_manifest is not None
        or args.task035d_selective_face_coarse_manifest_sha256 is not None
    ):
        parser.error("Task035d variable-p arguments require --task035d-case097-gate.")
    if (
        args.stage4_full3d_assembly_backend
        in {
            "assembly_time_static_condensed",
            TASK035D_CASE097_BACKEND,
        }
        and args.run_kind != "full-solve"
    ):
        parser.error(
            "assembly-time condensed backends require --run-kind full-solve "
            "for mandatory recovery and explicit residual."
        )
    if not args.worker and (
        args.parent_launch_descriptor is not None
        or args.parent_launch_descriptor_sha256 is not None
    ):
        parser.error("parent-launch descriptor options are internal worker arguments.")
    return args


def _validate_task035c_p6_preflight(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if not args.task035c_p6_h10_gate:
        return None
    path = args.task035c_p6_preflight_authority
    if path is None:
        raise SystemExit("Task035c p6/h10 preflight authority path is required.")
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 preflight authority is unreadable: {exc}"
        ) from exc
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        relative = None
    tracked = bool(
        relative is not None
        and subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    gate = task035c_p6_h10_preflight_authority_gate(
        record if isinstance(record, dict) else None,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=_sha256(path),
        authority_is_tracked=tracked,
    )
    gate["path"] = _path_from_root(path)
    if not gate["pass"]:
        raise SystemExit(
            f"Task035c p6/h10 preflight authority failed: {gate['failures']}"
        )
    return gate


def _validate_task035d_case097_plan(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if not args.task035d_case097_gate:
        return None
    local_h_candidate = args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
    plan_path = (
        args.stage4_local_h_refinement_plan
        if local_h_candidate
        else args.stage4_variable_p_cell_degree_plan
    )
    authority_path = args.task035d_plan_authority
    if plan_path is None or authority_path is None:
        raise SystemExit("Task035d Case097 plan and MPI8 authority paths are required.")
    plan_path = (plan_path if plan_path.is_absolute() else ROOT / plan_path).resolve()
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d Case097 launch authority is unreadable: {exc}"
        ) from exc

    def tracked(path: Path) -> tuple[bool, str | None]:
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            return False, None
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0, relative

    plan_tracked, plan_relative = tracked(plan_path)
    authority_tracked, authority_relative = tracked(authority_path)
    if args.task035d_candidate_id == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME:
        gate_builder = task035d_case097_hp_factorial_bridge_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_LEFT_GRATING_TOP_PLAN_NAME:
        gate_builder = task035d_case097_left_grating_top_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_COMBINED_HP_PLAN_NAME:
        gate_builder = task035d_case097_combined_hp_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME:
        gate_builder = task035d_case097_selective_face_plan_authority_gate
    elif local_h_candidate:
        gate_builder = task035d_case097_local_h_plan_authority_gate
    elif args.task035d_candidate_id == "sidewall_z0_guard_v1":
        gate_builder = task035d_case097_sidewall_guard_plan_authority_gate
    else:
        gate_builder = task035d_case097_plan_authority_gate
    gate = gate_builder(
        plan if isinstance(plan, dict) else None,
        authority if isinstance(authority, dict) else None,
        expected_plan_file_sha256=(
            args.stage4_local_h_refinement_plan_sha256
            if local_h_candidate
            else args.stage4_variable_p_cell_degree_plan_sha256
        ),
        observed_plan_file_sha256=_sha256(plan_path),
        expected_authority_sha256=args.task035d_plan_authority_sha256,
        observed_authority_sha256=_sha256(authority_path),
        plan_is_tracked=plan_tracked,
        authority_is_tracked=authority_tracked,
        plan_path_from_root=plan_relative,
        authority_path_from_root=authority_relative,
    )
    gate["plan_path"] = _path_from_root(plan_path)
    gate["authority_path"] = _path_from_root(authority_path)
    gate["authority_path_from_root"] = authority_relative
    if not gate["pass"]:
        raise SystemExit(
            f"Task035d Case097 {args.task035d_candidate_id} launch "
            "authority failed: "
            f"{gate['failures']}"
        )
    if local_h_candidate:
        args.stage4_local_h_refinement_plan = plan_path
    else:
        args.stage4_variable_p_cell_degree_plan = plan_path
    args.task035d_plan_authority = authority_path
    return gate


def _validate_task035d_nested_p_inputs(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    phase = args.task035d_nested_p_dwr_phase
    if phase is None:
        return None
    pair_path = args.task035d_nested_p_pair_authority
    if pair_path is None:
        raise SystemExit("Task035d nested-p A/B pair authority is required.")
    pair_path = (pair_path if pair_path.is_absolute() else ROOT / pair_path).resolve()
    try:
        pair_authority = json.loads(pair_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d nested-p pair authority is unreadable: {exc}"
        ) from exc
    if not isinstance(pair_authority, dict):
        pair_authority = {}
    try:
        pair_relative = pair_path.relative_to(ROOT).as_posix()
    except ValueError:
        pair_relative = None
    pair_tracked = bool(
        pair_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                pair_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    pair_sha = _sha256(pair_path)

    def load_pair_reference(
        entry: dict[str, Any],
        field: str,
    ) -> tuple[dict[str, Any] | None, dict[str, bool]]:
        reference = entry.get(field, {})
        raw_path = reference.get("path")
        expected_sha = reference.get("sha256")
        payload = None
        reference_path = None
        within_root = False
        tracked = False
        readable = False
        sha_matches = False
        if isinstance(raw_path, str):
            reference_path = (ROOT / raw_path).resolve()
            try:
                relative = reference_path.relative_to(ROOT).as_posix()
                within_root = True
            except ValueError:
                relative = None
            if within_root:
                tracked = (
                    subprocess.run(
                        [
                            "git",
                            "ls-files",
                            "--error-unmatch",
                            "--",
                            str(relative),
                        ],
                        cwd=ROOT,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                    == 0
                )
                try:
                    payload = json.loads(reference_path.read_text(encoding="utf-8"))
                    readable = isinstance(payload, dict)
                except (OSError, json.JSONDecodeError):
                    payload = None
                sha_matches = bool(
                    readable
                    and isinstance(expected_sha, str)
                    and _sha256(reference_path) == expected_sha
                )
        return payload, {
            "within_root": within_root,
            "tracked": tracked,
            "readable": readable,
            "sha256": sha_matches,
        }

    pair_reference_payloads: dict[str, dict[str, Any] | None] = {}
    pair_reference_checks: dict[str, dict[str, bool]] = {}
    for role_name, role in (
        ("coarse_B", pair_authority.get("coarse_B", {})),
        ("enriched_A", pair_authority.get("enriched_A", {})),
    ):
        role = role if isinstance(role, dict) else {}
        for field in ("plan", "mpi8_launch_authority"):
            payload, checks = load_pair_reference(role, field)
            key = f"{role_name}_{field}"
            pair_reference_payloads[key] = payload
            pair_reference_checks[key] = checks

    authority_path = args.task035d_significant_channel_authority
    if authority_path is None:
        raise SystemExit("Task035d nested-p significant-channel authority is required.")
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d nested-p significant-channel authority is unreadable: {exc}"
        ) from exc
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_tracked = bool(
        authority_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                authority_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    authority_sha = _sha256(authority_path)
    authority_checks = {
        "tracked": authority_tracked,
        "sha256": (authority_sha == args.task035d_significant_channel_authority_sha256),
        "schema": (
            authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
        ),
        "pass": authority.get("pass") is True,
        "twelve_channels": (
            authority.get("significant_channel_selection", {}).get("channel_count")
            == 12
            and len(authority.get("channels", ())) == 12
        ),
    }
    failures = [
        f"significant_channel_{name}"
        for name, passed in authority_checks.items()
        if not passed
    ]
    coarse_pair = pair_authority.get("coarse_B", {})
    coarse_pair = coarse_pair if isinstance(coarse_pair, dict) else {}
    enriched_pair = pair_authority.get("enriched_A", {})
    enriched_pair = enriched_pair if isinstance(enriched_pair, dict) else {}
    common_pair = pair_authority.get("frozen_common_identity", {})
    common_pair = common_pair if isinstance(common_pair, dict) else {}
    formal_contract = pair_authority.get("formal_run_contract", {})
    formal_contract = formal_contract if isinstance(formal_contract, dict) else {}
    stable_identity_keys = (
        "base_config_identity_sha256",
        "leaf_catalog_sha256",
        "hanging_face_catalog_sha256",
        "carrier_connectivity_sha256",
        "material_catalog_sha256",
        "physical_facet_catalog_sha256",
        "physical_authority_sha256",
        "flattened_graph_sha256",
        "canonical_cell_graph_sha256",
    )
    common_stable_identity_matches = all(
        all(
            payload is not None
            and payload.get("stable_identity", {}).get(key) == common_pair.get(key)
            for payload in (
                pair_reference_payloads["coarse_B_mpi8_launch_authority"],
                pair_reference_payloads["enriched_A_mpi8_launch_authority"],
            )
        )
        for key in stable_identity_keys
    )
    common_root_identity_matches = all(
        payload is not None
        and payload.get("root_cell_box_catalog_sha256")
        == common_pair.get("root_cell_box_catalog_sha256")
        and payload.get("expected_forest", {}).get("root_catalog_sha256")
        == common_pair.get("root_catalog_sha256")
        for payload in (
            pair_reference_payloads["coarse_B_plan"],
            pair_reference_payloads["enriched_A_plan"],
        )
    )
    active_pair = coarse_pair if phase == "coarse-snapshot" else enriched_pair
    expected_candidate = (
        TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
        if phase == "coarse-snapshot"
        else TASK035D_LOCAL_H_PLAN_NAME
    )
    pair_checks = {
        "tracked": pair_tracked,
        "sha256": (pair_sha == args.task035d_nested_p_pair_authority_sha256),
        "schema": (
            pair_authority.get("schema_version")
            == "task035d.same-trace-nested-p-pair-authority.v1"
        ),
        "pass": pair_authority.get("pass") is True,
        "same_trace_only": (
            pair_authority.get("scope", {}).get("same_trace_only") is True
            and pair_authority.get("scope", {}).get("cross_trace_primal_prolongation")
            is False
            and pair_authority.get("scope", {}).get("dense_local_schur_persistence")
            is False
        ),
        "mpi8": (pair_authority.get("scope", {}).get("mpi_size") == 8),
        "referenced_files": all(
            all(checks.values()) for checks in pair_reference_checks.values()
        ),
        "common_stable_identity": common_stable_identity_matches,
        "common_root_identity": common_root_identity_matches,
        "coarse_candidate": (
            coarse_pair.get("candidate_id") == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
        ),
        "enriched_candidate": (
            enriched_pair.get("candidate_id") == TASK035D_LOCAL_H_PLAN_NAME
        ),
        "coarse_degree_and_dof_contract": (
            coarse_pair.get("cell_interior_degree_counts") == {"p5": 32, "p6": 102}
            and coarse_pair.get("actual_full3d_equivalent_active_fe_dofs") == 76_205
            and coarse_pair.get("reduced_trace_plus_auxiliary_rows") == 18_470
        ),
        "enriched_degree_and_dof_contract": (
            enriched_pair.get("cell_interior_degree_counts") == {"p5": 0, "p6": 134}
            and enriched_pair.get("actual_full3d_equivalent_active_fe_dofs") == 82_925
            and enriched_pair.get("reduced_trace_plus_auxiliary_rows") == 18_470
        ),
        "active_candidate": (
            active_pair.get("candidate_id")
            == expected_candidate
            == args.task035d_candidate_id
        ),
        "active_plan": (
            active_pair.get("plan", {}).get("sha256")
            == args.stage4_local_h_refinement_plan_sha256
        ),
        "active_launch_authority": (
            active_pair.get("mpi8_launch_authority", {}).get("sha256")
            == args.task035d_plan_authority_sha256
        ),
        "common_rows": (
            common_pair.get("leaf_cell_count") == 134
            and common_pair.get("trace_degree") == 5
            and common_pair.get("raw_trace_rows") == 23_875
            and common_pair.get("independent_trace_rows") == 18_390
            and common_pair.get("auxiliary_rows") == 80
            and common_pair.get("reduced_rows") == 18_470
        ),
        "same_channel_authority": (
            pair_authority.get("significant_channel_authority", {}).get("sha256")
            == authority_sha
        ),
        "formal_residual_contract": (
            formal_contract.get("coarse_full_explicit_true_residual_max") == 1.0e-9
            and formal_contract.get("enriched_full_explicit_true_residual_max")
            == 1.0e-9
            and formal_contract.get("unit_channel_adjoint_relative_residual_max")
            == 1.0e-9
        ),
        "formal_goal_contract": (
            formal_contract.get("unit_channel_adjoint_solve_count") == 12
            and formal_contract.get("all_36_signed_goal_closures_required") is True
            and formal_contract.get(
                "trace_only_functional_roundoff_must_pass_"
                "recorded_scale_aware_threshold"
            )
            is True
            and formal_contract.get(
                "trace_only_external_operator_content_sha_match_required"
            )
            is True
            and formal_contract.get(
                "trace_only_external_rhs_content_sha_match_required"
            )
            is True
            and formal_contract.get(
                "external_delta_may_be_derived_from_complete_minus_cell"
            )
            is False
            and formal_contract.get("unexplained_residual_may_be_added_back") is False
            and formal_contract.get("absolute_indicator_sum_may_close_goals") is False
        ),
    }
    failures.extend(
        f"pair_authority_{name}" for name, passed in pair_checks.items() if not passed
    )
    snapshot_gate = None
    if phase == "enriched-evaluate":
        snapshot_path = args.task035d_coarse_snapshot_manifest
        if snapshot_path is None:
            raise SystemExit(
                "Task035d enriched nested-p DWR requires a coarse manifest."
            )
        snapshot_path = (
            snapshot_path if snapshot_path.is_absolute() else ROOT / snapshot_path
        ).resolve()
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Task035d coarse snapshot is unreadable: {exc}") from exc
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot_artifact_gate = task035d_coarse_snapshot_artifact_gate(
            snapshot_path,
            snapshot,
            expected_mpi_size=8,
            expected_cell_count=134,
        )
        snapshot_checks = {
            "sha256": (
                _sha256(snapshot_path) == args.task035d_coarse_snapshot_manifest_sha256
            ),
            "schema": (
                snapshot.get("schema_version")
                == "task035d.variable-p-nested-coarse-snapshot.v1"
            ),
            "pass": snapshot.get("pass") is True,
            "role": snapshot.get("role") == "coarse_B",
            "candidate": (
                snapshot.get("candidate", {}).get("candidate_id")
                == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
            ),
            "candidate_plan": (
                snapshot.get("candidate", {}).get("plan_file_sha256")
                == coarse_pair.get("plan", {}).get("sha256")
            ),
            "candidate_degree_counts": (
                snapshot.get("candidate", {}).get("cell_interior_degree_counts")
                == {"5": 32, "6": 102}
            ),
            "candidate_dofs": (
                snapshot.get("candidate", {}).get(
                    "actual_full3d_equivalent_active_fe_dofs"
                )
                == 76_205
            ),
            "source": (
                snapshot.get("candidate", {}).get("source_sha")
                == args.verified_clean_sha
            ),
            "mpi8": (snapshot.get("same_trace_identity", {}).get("mpi_size") == 8),
            "trace_rows": (
                snapshot.get("same_trace_identity", {}).get("independent_trace_rows")
                == 18_390
            ),
            "matrix_rows": (
                snapshot.get("same_trace_identity", {}).get("matrix_rows") == 18_470
            ),
            "auxiliary_rows": (
                snapshot.get("same_trace_identity", {}).get("auxiliary_rows") == 80
            ),
            "same_channel_authority": (
                snapshot.get(
                    "significant_channel_authority",
                    {},
                ).get("sha256")
                == authority_sha
            ),
            "all_shards_preflight": (snapshot_artifact_gate["pass"] is True),
            "trace_only_port_operator_content": (
                snapshot.get("port_operator_audit", {}).get("pass") is True
                and all(
                    snapshot.get("port_operator_audit", {}).get("checks", {}).values()
                )
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "removed_active_interior_over_threshold_max"
                    ),
                    (int, float),
                )
                and 0.0
                <= float(
                    snapshot["port_operator_audit"][
                        "removed_active_interior_over_threshold_max"
                    ]
                )
                <= 1.0
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "external_operator_content_sha256"
                    ),
                    str,
                )
                and len(
                    snapshot["port_operator_audit"]["external_operator_content_sha256"]
                )
                == 64
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "external_rhs_content_sha256"
                    ),
                    str,
                )
                and len(snapshot["port_operator_audit"]["external_rhs_content_sha256"])
                == 64
            ),
            "primal_residual_gate": (
                snapshot.get("primal_residual_gate", {}).get("pass") is True
                and all(
                    snapshot.get("primal_residual_gate", {}).get("checks", {}).values()
                )
                and isinstance(
                    snapshot.get("vector_identity", {}).get("relative_residual"),
                    (int, float),
                )
                and float(snapshot["vector_identity"]["relative_residual"]) <= 1.0e-9
                and isinstance(
                    snapshot.get("full_active_residual", {}).get(
                        "linear_system_relative_residual"
                    ),
                    (int, float),
                )
                and float(
                    snapshot["full_active_residual"]["linear_system_relative_residual"]
                )
                <= 1.0e-9
            ),
        }
        failures.extend(
            f"coarse_snapshot_{name}"
            for name, passed in snapshot_checks.items()
            if not passed
        )
        snapshot_gate = {
            "path": _path_from_root(snapshot_path),
            "sha256": _sha256(snapshot_path),
            "checks": snapshot_checks,
            "artifact_gate": snapshot_artifact_gate,
        }
        args.task035d_coarse_snapshot_manifest = snapshot_path
    args.task035d_significant_channel_authority = authority_path
    args.task035d_nested_p_pair_authority = pair_path
    gate = {
        "schema_version": "task035d.nested-p-launch-gate.v1",
        "phase": phase,
        "pass": not failures,
        "failures": failures,
        "significant_channel_authority": {
            "path": _path_from_root(authority_path),
            "sha256": authority_sha,
            "checks": authority_checks,
        },
        "nested_p_pair_authority": {
            "path": _path_from_root(pair_path),
            "sha256": pair_sha,
            "checks": pair_checks,
            "referenced_file_checks": pair_reference_checks,
        },
        "coarse_snapshot": snapshot_gate,
        "same_trace_only": True,
        "cross_trace_primal_prolongation": False,
    }
    if failures:
        raise SystemExit(f"Task035d nested-p launch inputs failed: {failures}")
    return gate


def _validate_task035d_selective_face_inputs(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Validate the cross-trace endpoint pair without same-trace shortcuts."""

    phase = args.task035d_selective_face_dwr_phase
    if phase is None:
        return None
    authority_path = args.task035d_significant_channel_authority
    if authority_path is None:
        raise SystemExit(
            "Task035d selective-face significant-channel authority is required."
        )
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Task035d selective-face significant-channel authority is "
            f"unreadable: {exc}"
        ) from exc
    if not isinstance(authority, dict):
        raise SystemExit(
            "Task035d selective-face significant-channel authority must be "
            "one JSON object."
        )
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_tracked = bool(
        authority_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                authority_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    authority_sha = _sha256(authority_path)
    authority_checks = {
        "tracked": authority_tracked,
        "sha256": (authority_sha == args.task035d_significant_channel_authority_sha256),
        "schema": (
            authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
        ),
        "pass": authority.get("pass") is True,
        "twelve_channels": (
            authority.get("significant_channel_selection", {}).get("channel_count")
            == 12
            and len(authority.get("channels", ())) == 12
        ),
    }
    failures = [
        f"significant_channel_{name}"
        for name, passed in authority_checks.items()
        if not passed
    ]
    snapshot_gate = None
    if phase == "enriched-evaluate":
        snapshot_path = args.task035d_selective_face_coarse_manifest
        if snapshot_path is None:
            raise SystemExit(
                "Task035d selective-face enriched phase requires the coarse manifest."
            )
        snapshot_path = (
            snapshot_path if snapshot_path.is_absolute() else ROOT / snapshot_path
        ).resolve()
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(
                f"Task035d selective-face coarse manifest is unreadable: {exc}"
            ) from exc
        if not isinstance(snapshot, dict):
            raise SystemExit(
                "Task035d selective-face coarse manifest must be one JSON object."
            )
        arrays_path = snapshot_path.parent / str(
            snapshot.get("arrays", {}).get("path", "")
        )
        observed_arrays_sha = (
            _sha256(arrays_path)
            if arrays_path.parent == snapshot_path.parent and arrays_path.is_file()
            else None
        )
        snapshot_artifact_gate = task035d_selective_face_coarse_snapshot_gate(
            snapshot,
            expected_source_sha=str(args.verified_clean_sha),
            expected_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
            expected_significant_channel_authority_sha256=(
                str(args.task035d_significant_channel_authority_sha256)
            ),
            observed_arrays_sha256=observed_arrays_sha,
        )
        snapshot_checks = {
            "provided_manifest_sha256": (
                _sha256(snapshot_path)
                == args.task035d_selective_face_coarse_manifest_sha256
            ),
            "artifact_gate": snapshot_artifact_gate["pass"] is True,
        }
        failures.extend(
            f"coarse_snapshot_{name}"
            for name, passed in snapshot_checks.items()
            if not passed
        )
        snapshot_gate = {
            "path": _path_from_root(snapshot_path),
            "sha256": _sha256(snapshot_path),
            "arrays_path": _path_from_root(arrays_path),
            "arrays_sha256": observed_arrays_sha,
            "checks": snapshot_checks,
            "artifact_gate": snapshot_artifact_gate,
        }
        args.task035d_selective_face_coarse_manifest = snapshot_path
    args.task035d_significant_channel_authority = authority_path
    gate_checks = {
        "significant_channel_authority": (
            bool(authority_checks)
            and all(value is True for value in authority_checks.values())
        ),
        "phase_endpoint_scope": (
            (
                phase == "coarse-snapshot"
                and args.task035d_candidate_id == TASK035D_LOCAL_H_PLAN_NAME
            )
            or (
                phase == "enriched-evaluate"
                and args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME
            )
        ),
        "coarse_snapshot": (
            snapshot_gate is None
            if phase == "coarse-snapshot"
            else bool(
                snapshot_gate
                and snapshot_gate["checks"]["provided_manifest_sha256"] is True
                and snapshot_gate["checks"]["artifact_gate"] is True
            )
        ),
        "cross_trace_without_dense_schur": True,
    }
    failures.extend(name for name, passed in gate_checks.items() if not passed)
    failures = list(dict.fromkeys(failures))
    gate = {
        "schema_version": ("task035d.selective-face-cross-trace-launch-gate.v1"),
        "phase": phase,
        "pass": not failures,
        "checks": gate_checks,
        "failures": failures,
        "significant_channel_authority": {
            "path": _path_from_root(authority_path),
            "sha256": authority_sha,
            "checks": authority_checks,
        },
        "coarse_snapshot": snapshot_gate,
        "same_trace_only": False,
        "cross_trace_primal_prolongation": True,
        "dense_local_schur_persistence": False,
    }
    if failures:
        raise SystemExit(f"Task035d selective-face launch inputs failed: {failures}")
    return gate


def _validate_p4_gate(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.degree != 4:
        return None
    if args.p3_gate_record is None:
        raise SystemExit("p4 is locked: --p3-gate-record is required.")
    if args.p4_trace_record is None:
        raise SystemExit("p4 is locked: --p4-trace-record is required.")
    path = (
        args.p3_gate_record
        if args.p3_gate_record.is_absolute()
        else ROOT / args.p3_gate_record
    )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"p4 is locked: cannot read p3 gate record: {exc}") from exc
    resource = record.get("resource_authority") or {}
    memory = resource.get("memory_authority_gib")
    workstation_h3 = bool(args.task034_p4_h3_added_point)
    memory_threshold_gib = (
        float(args.warning_gib)
        if workstation_h3 and isinstance(args.warning_gib, (int, float))
        else 10.0
    )
    memory_gate_name = (
        "memory_below_live_task034_warning" if workstation_h3 else "memory_below_10_gib"
    )
    checks = {
        "p3_degree": record.get("degree") == 3,
        "same_h": float(record.get("h_nm", -1.0)) == args.h_nm,
        "full_solve": record.get("run_kind") == "full-solve",
        "reference_pass": record.get("status") == "full3d_reference_pass",
        "no_swap": record.get("no_swap") is True,
        memory_gate_name: isinstance(memory, (int, float))
        and float(memory) < memory_threshold_gib,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise SystemExit(f"p4 is locked; failed p3 gates: {failures}")
    trace_path = (
        args.p4_trace_record
        if args.p4_trace_record.is_absolute()
        else ROOT / args.p4_trace_record
    )
    try:
        trace_record = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"p4 is locked: cannot read four-mode trace record: {exc}"
        ) from exc
    trace_gates = trace_record.get("gates") or {}
    trace_checks = {
        "record_type": (
            trace_record.get("record_type") == "p4_four_mode_matched_trace_aggregate"
        ),
        "status": (trace_record.get("status") == "p4_four_mode_matched_trace_pass"),
        "four_mode_trace_pass": (trace_gates.get("p4_four_mode_matched_trace") is True),
        "mpi_identity_pass": (trace_gates.get("mpi1_mpi4_compact_identity") is True),
        "same_current_source": (
            trace_record.get("source_commit_sha") == args.verified_clean_sha
        ),
    }
    trace_failures = [name for name, passed in trace_checks.items() if not passed]
    if trace_failures:
        raise SystemExit(
            f"p4 is locked; failed four-mode trace gates: {trace_failures}"
        )
    return {
        "p3": {
            "path": _path_from_root(path),
            "sha256": _sha256(path),
            "checks": checks,
        },
        "p4_four_mode_trace": {
            "path": _path_from_root(trace_path),
            "sha256": _sha256(trace_path),
            "checks": trace_checks,
        },
        "task034_p4_h3_added_point": workstation_h3,
        "p3_memory_threshold_gib": memory_threshold_gib,
        "pass": True,
    }


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    def delta(name: str) -> int | None:
        values = [
            int(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) - min(values) if values else None

    worker_mb = maximum("worker_rank_rss_sum_mb")
    worker_pss_mb = maximum("worker_rank_pss_sum_mb")
    worker_uss_mb = maximum("worker_rank_uss_sum_mb")
    worker_shared_mb = maximum("worker_rank_shared_sum_mb")
    worker_smaps_swap_mb = maximum("worker_rank_smaps_swap_sum_mb")
    process_tree_mb = maximum("mpi_process_tree_rss_mb")
    process_tree_swap_mb = maximum("mpi_process_tree_swap_mb")
    dedicated_rows = [row for row in rows if row.get("job_cgroup_dedicated") is True]
    observed_cgroup_current_mb = maximum("container_cgroup_current_mb")
    observed_cgroup_swap_mb = maximum("container_swap_current_mb")
    dedicated_cgroup_values = [
        float(row["container_cgroup_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_cgroup_current_mb"), (int, float))
    ]
    dedicated_swap_values = [
        float(row["container_swap_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_swap_current_mb"), (int, float))
    ]
    cgroup_mb = max(dedicated_cgroup_values) if dedicated_cgroup_values else None
    swap_mb = max(dedicated_swap_values) if dedicated_swap_values else None
    cgroup_peak_mb = maximum("container_cgroup_peak_mb")
    memory_authority_mb = (
        None
        if process_tree_mb is None
        else max(process_tree_mb, float(cgroup_mb or 0.0))
    )
    combined_authority_mb = memory_authority_mb
    worker_rank_counts: list[int] = []
    per_rank_smaps_peaks: dict[str, dict[str, float]] = {}
    per_rank_rss_peaks: dict[str, float] = {}
    fully_readable_mpi8_smaps_sample_count = 0
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_rank_counts.append(len(workers))
            for worker in workers:
                if not isinstance(worker, dict):
                    continue
                rank = worker.get("rank")
                rss = worker.get("rss_mb")
                if isinstance(rank, int) and isinstance(rss, (int, float)):
                    key = str(rank)
                    per_rank_rss_peaks[key] = max(
                        per_rank_rss_peaks.get(key, 0.0),
                        float(rss),
                    )
        try:
            smaps = json.loads(str(row.get("worker_rank_smaps_rollup_json", "[]")))
        except json.JSONDecodeError:
            continue
        if not isinstance(smaps, list):
            continue
        smaps_ranks = {
            worker.get("rank")
            for worker in smaps
            if isinstance(worker, dict) and isinstance(worker.get("rank"), int)
        }
        if row.get("worker_rank_smaps_readable_count") == 8 and smaps_ranks == set(
            range(8)
        ):
            fully_readable_mpi8_smaps_sample_count += 1
        for worker in smaps:
            if not isinstance(worker, dict) or not isinstance(
                worker.get("rank"),
                int,
            ):
                continue
            key = str(worker["rank"])
            peaks = per_rank_smaps_peaks.setdefault(key, {})
            for name in (
                "rss_mb",
                "pss_mb",
                "uss_mb",
                "shared_mb",
                "anonymous_mb",
                "swap_mb",
                "swap_pss_mb",
            ):
                value = worker.get(name)
                if isinstance(value, (int, float)):
                    peaks[name] = max(
                        peaks.get(name, 0.0),
                        float(value),
                    )
    return {
        "poll_interval_seconds": None,
        "sample_count": len(rows),
        "max_simultaneous_worker_rss_mb": worker_mb,
        "max_simultaneous_worker_pss_mb": worker_pss_mb,
        "max_simultaneous_worker_uss_mb": worker_uss_mb,
        "max_simultaneous_worker_shared_mb": worker_shared_mb,
        "max_simultaneous_worker_smaps_swap_mb": worker_smaps_swap_mb,
        "per_rank_rss_peak_mb": per_rank_rss_peaks,
        "per_rank_smaps_rollup_peak_mb": per_rank_smaps_peaks,
        "max_worker_rank_smaps_readable_count": maximum(
            "worker_rank_smaps_readable_count"
        ),
        "fully_readable_mpi8_smaps_sample_count": (
            fully_readable_mpi8_smaps_sample_count
        ),
        "max_process_tree_rss_mb": process_tree_mb,
        "max_process_tree_swap_mb": process_tree_swap_mb,
        "dedicated_job_cgroup_observed": bool(dedicated_rows),
        "max_container_cgroup_current_mb": cgroup_mb,
        "max_container_cgroup_peak_mb": cgroup_peak_mb,
        "max_container_swap_current_mb": swap_mb,
        "max_container_cgroup_current_observed_mb": (observed_cgroup_current_mb),
        "max_container_swap_current_observed_mb": observed_cgroup_swap_mb,
        "memory_authority_mb": memory_authority_mb,
        "memory_authority_gib": (
            None if memory_authority_mb is None else memory_authority_mb / 1024.0
        ),
        "combined_memory_swap_authority_mb": combined_authority_mb,
        "combined_memory_swap_authority_gib": (
            None if combined_authority_mb is None else combined_authority_mb / 1024.0
        ),
        "max_observed_worker_rank_count": (
            max(worker_rank_counts) if worker_rank_counts else 0
        ),
        "pswpin_delta_pages": delta("wsl_pswpin_pages"),
        "pswpout_delta_pages": delta("wsl_pswpout_pages"),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _factorization_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "before_ksp_setup",
            "after_ksp_setup_factorized",
            "before_ksp_solve",
            "after_ksp_solve",
        }
        for event in events
    )


def _solve_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "stage4_dtn_augmented_solve",
            "before_ksp_solve",
            "during_ksp_solve_peak",
            "after_ksp_solve",
        }
        for event in events
    )


def _qualify_task037_e2_modal_capacity(
    audit: dict[str, Any],
    *,
    solver_summary: dict[str, Any],
    return_code: int,
    no_swap: bool,
) -> dict[str, Any]:
    from src.solvers.static_modal_capacity_oracle import (
        qualify_e2_capacity_audit,
    )

    checker = qualify_e2_capacity_audit(audit)
    checks = {
        "process_completed": return_code == 0,
        "no_swap": no_swap,
        "external_linear_solver_port": (
            solver_summary.get("external_linear_solver_port") is True
        ),
        "official_result_absent": solver_summary.get("official_result") is False,
        "capacity_checker_pass": checker["pass"] is True,
    }
    failures = [name for name, passed in checks.items() if not passed]
    classification = checker["classification"]
    if not checker["pass"] and checker.get("status") == "capacity_negative":
        classification = (
            "M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS"
        )
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "classification": classification,
        "capacity_checker": checker,
        "b4_solver_gate_independent": audit.get("solver_convergence_gate"),
        "raw_capacity_gate_pass": audit.get("capacity_gate_pass"),
    }


def _qualify_task037_e2_b4_snapshot(
    audit: dict[str, Any],
    *,
    solver_summary: dict[str, Any],
    return_code: int,
    no_swap: bool,
) -> dict[str, Any]:
    samples = audit.get("true_residual_samples")
    by_iteration = (
        {int(item["iteration"]): item for item in samples}
        if isinstance(samples, list)
        else {}
    )
    config = audit.get("config")
    config = config if isinstance(config, dict) else {}
    manifest = audit.get("manifest")
    manifest = manifest if isinstance(manifest, dict) else {}
    factor_inventory = audit.get("p6_factor_inventory")
    factor_inventory = (
        factor_inventory if isinstance(factor_inventory, dict) else {}
    )
    values = {
        iteration: (
            by_iteration.get(iteration, {}).get("relative_true_residual")
        )
        for iteration in TASK037_E2_B4_ITERATIONS
    }
    checks = {
        "process_completed": return_code == 0,
        "iterations_exact": tuple(sorted(by_iteration)) == TASK037_E2_B4_ITERATIONS,
        "finite_samples": all(
            isinstance(item, dict)
            and item.get("global_rows") == 51192
            and _finite_number_le(item.get("relative_true_residual"), 1.0e300)
            for item in by_iteration.values()
        )
        and len(by_iteration) == len(TASK037_E2_B4_ITERATIONS),
        "core_scalar_identity": all(
            isinstance(values[iteration], (int, float))
            and isinstance(
                by_iteration.get(iteration, {}).get("core_relative_true_residual"),
                (int, float),
            )
            and abs(
                float(values[iteration])
                - float(
                    by_iteration[iteration]["core_relative_true_residual"]
                )
            )
            <= 1.0e-12
            for iteration in TASK037_E2_B4_ITERATIONS
        ),
        "owner_local_storage": (
            audit.get("carrier_gate_pass") is True
            and audit.get("source_sha") == manifest.get("source_sha")
            and audit.get("owner_local") is True
            and audit.get("replicated_global_vector") is False
            and manifest.get("owner_local") is True
            and manifest.get("replicated_global_basis") is False
            and manifest.get("source_sha") == audit.get("source_sha")
            and manifest.get("global_rows") == 51192
            and manifest.get("column_count") == 4
            and manifest.get("shard_count", 0) == 8
        ),
        "global_A_F_unmaterialized": (
            config.get("global_A_materialized") is False
            and config.get("global_F_materialized") is False
        ),
        "solver_profile": (
            audit.get("solver_profile")
            == "never_materialized_p2_factor_free_slab_auxiliary"
        ),
        "restart": config.get("restart") == 90,
        "max_it": config.get("screen_iterations") == 200,
        "local_krylov_steps": config.get("local_krylov_steps") == 4,
        "overlap_fraction": config.get("overlap_fraction") == 0.125,
        "partition": config.get("partition") == "partition",
        "p6_factor_count": factor_inventory.get("p6_factor_count") == 0,
        "p6_factor_nnz": factor_inventory.get("p6_factor_nnz") == 0,
        "no_swap": no_swap,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "classification": (
            "task037_e2_b4_snapshot_carrier_pass"
            if not failures
            else "task037_e2_b4_snapshot_carrier_not_pass"
        ),
        "b4_solver_gate_independent": audit.get("solver_convergence_gate"),
        "raw_carrier_gate_pass": audit.get("carrier_gate_pass"),
        "external_linear_solver_port": (
            solver_summary.get("external_linear_solver_port")
        ),
    }


def _qualify(
    *,
    args: argparse.Namespace,
    solver_summary: dict[str, Any],
    events: list[dict[str, Any]],
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    terminated_for_authority_unreadable: bool,
    no_swap: bool,
    observed_worker_rank_count: int | None = None,
    resource_summary: dict[str, Any] | None = None,
    task037_f3_core_audit: dict[str, Any] | None = None,
    task037_e1_audit: dict[str, Any] | None = None,
    task037_e2_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matrix = solver_summary.get("matrix_stats") or {}
    e1_gate = bool(getattr(args, "task037_e1_modal_basis_gate", False))
    e2_gate = bool(getattr(args, "task037_e2_b4_snapshot_carrier", False))
    e2_capacity_gate = bool(
        getattr(args, "task037_e2_modal_capacity_gate", False)
    )
    m3a_profile = bool(args.task037_m3a_overlap0125_partition)
    m4_optimized_schwarz_profile = bool(args.task037_m4_optimized_schwarz)
    m4_factor_free_profile = bool(
        args.task037_m4_factor_free_slab and not m4_optimized_schwarz_profile
    )
    m4_profile = bool(
        args.task037_m4_p2_auxiliary
        and not m4_factor_free_profile
        and not m4_optimized_schwarz_profile
    )
    m2c_profile = bool(
        args.task037_m2c_never_materialized
        and not m3a_profile
        and not m4_profile
        and not m4_factor_free_profile
        and not m4_optimized_schwarz_profile
    )
    action_only_profile = (
        bool(args.task037_e0_matrix_free_dtn_gate)
        or e1_gate
        or e2_gate
        or e2_capacity_gate
        or m2c_profile
        or m3a_profile
        or m4_profile
        or m4_factor_free_profile
        or m4_optimized_schwarz_profile
    )
    condensation = solver_summary.get("cell_static_condensation") or {}
    common = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "live_authority_readable": not terminated_for_authority_unreadable,
        "all_expected_mpi_ranks_observed": (
            observed_worker_rank_count is None
            or observed_worker_rank_count == args.mpi_size
        ),
        "exact_positive_rows": (
            isinstance(matrix.get("matrix_rows"), (int, float))
            and float(matrix["matrix_rows"]) > 0.0
        ),
        "exact_positive_assembled_nnz": (
            action_only_profile
            or (
                isinstance(matrix.get("matrix_nnz_used"), (int, float))
                and float(matrix["matrix_nnz_used"]) > 0.0
            )
        ),
        "polarization_identity": (
            solver_summary.get("polarization_kind") == args.polarization_kind
        ),
    }
    if e2_capacity_gate:
        e2_checker = _qualify_task037_e2_modal_capacity(
            task037_e2_audit if isinstance(task037_e2_audit, dict) else {},
            solver_summary=solver_summary,
            return_code=return_code,
            no_swap=no_swap,
        )
        checks = {
            **common,
            "e2_capacity_audit_present": isinstance(task037_e2_audit, dict)
            and bool(task037_e2_audit),
            "e2_capacity_action_only": (
                solver_summary.get("external_linear_solver_port") is True
            ),
            "e2_capacity_no_official_result": (
                solver_summary.get("official_result") is False
            ),
            "e2_capacity_checker_pass": e2_checker["pass"] is True,
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "pass": not failures,
            "checks": checks,
            "failures": failures,
            "e2_capacity_checker": e2_checker,
            "e2_capacity_checker_classification": e2_checker.get(
                "classification"
            ),
            "task035d_case097_solver_gate": None,
        }
    if e2_gate:
        e2_checker = _qualify_task037_e2_b4_snapshot(
            task037_e2_audit if isinstance(task037_e2_audit, dict) else {},
            solver_summary=solver_summary,
            return_code=return_code,
            no_swap=no_swap,
        )
        checks = {
            **common,
            "e2_audit_present": isinstance(task037_e2_audit, dict)
            and bool(task037_e2_audit),
            "e2_action_only": (
                solver_summary.get("external_linear_solver_port") is True
            ),
            "e2_no_official_result": solver_summary.get("official_result") is False,
            "e2_checker_pass": e2_checker["pass"] is True,
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "pass": not failures,
            "checks": checks,
            "failures": failures,
            "e2_checker": e2_checker,
            "e2_checker_classification": e2_checker.get("classification"),
            "task035d_case097_solver_gate": None,
        }
    if e1_gate:
        from src.solvers.static_modal_coarse_gate import (
            qualify_e1_modal_basis_audit,
        )

        audit = task037_e1_audit if isinstance(task037_e1_audit, dict) else {}
        e1_checker = qualify_e1_modal_basis_audit(
            audit,
            solver_summary=solver_summary,
            return_code=return_code,
            no_swap=no_swap,
        )
        checks = {
            **common,
            "e1_action_only": (
                solver_summary.get("external_linear_solver_port") is True
            ),
            "e1_no_global_A_or_F": (
                matrix.get("global_A_materialized") is False
                and matrix.get("global_F_materialized") is False
            ),
            "e1_audit_present": bool(audit),
            "e1_audit_checker_pass": e1_checker["pass"] is True,
            "e1_external_component_profile": (
                solver_summary.get("external_solver_profile")
                == "task037_e1_component_only"
            ),
            "e1_no_factorization_or_solve_event": (
                not _factorization_stage_seen(events) and not _solve_stage_seen(events)
            ),
            "e1_no_ksp_iterations": solver_summary.get("ksp_iterations") == 0,
            "e1_no_official_result": (solver_summary.get("official_result") is False),
            "no_swap": no_swap,
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "pass": not failures,
            "checks": checks,
            "failures": failures,
            "e1_checker": e1_checker,
            "e1_checker_classification": e1_checker.get("classification"),
            "task035d_case097_solver_gate": None,
        }
    if args.task037_e0_matrix_free_dtn_gate:
        audit = solver_summary.get("matrix_free_dtn_probe_audit")
        audit = audit if isinstance(audit, dict) else {}
        mode_identity = audit.get("mode_identity")
        materialization = audit.get("materialization")
        primary_materialization = (
            materialization.get("primary") if isinstance(materialization, dict) else {}
        )
        oracle_materialization = (
            materialization.get("oracle") if isinstance(materialization, dict) else {}
        )
        source_audits = audit.get("source_audits")
        source_labels = (
            [item.get("label") for item in source_audits]
            if isinstance(source_audits, list)
            else []
        )
        checks = {
            **common,
            "e0_component_only": (
                solver_summary.get("matrix_free_dtn_component_only") is True
            ),
            "e0_probe_enabled": (solver_summary.get("matrix_free_dtn_probe") is True),
            "e0_case_status": (
                solver_summary.get("case_status") == "diagnostic_assemble_only"
            ),
            "e0_ordinary_default_unchanged": (
                solver_summary.get("ordinary_default_changed") is False
            ),
            "e0_audit_gate_pass": audit.get("gate_pass") is True,
            "e0_mode_identity_80": (
                isinstance(mode_identity, dict)
                and mode_identity.get("count") == 80
                and mode_identity.get("expected_count") == 80
                and audit.get("n_aux") == 80
                and mode_identity.get("primary_oracle_match") is True
            ),
            "e0_deterministic_seed_identity": (
                audit.get("deterministic_seeds") == [17037, 27037, 37037]
            ),
            "e0_source_audit_identity": (
                source_labels
                == [
                    "seed_17037",
                    "seed_27037",
                    "seed_37037",
                    "physical_active_rhs",
                ]
            ),
            "e0_forward_action_gate": _finite_number_le(
                audit.get("forward_action_relative_error_max"),
                1.0e-11,
            ),
            "e0_auxiliary_recovery_gate": _finite_number_le(
                audit.get("auxiliary_recovery_relative_error_max"),
                1.0e-11,
            ),
            "e0_physical_rhs_identity_gate": _finite_number_le(
                audit.get("physical_rhs_identity_relative_error"),
                1.0e-12,
            ),
            "e0_primary_c_d_materialization_zero": (
                primary_materialization.get("matrix_free_dtn") is True
                and primary_materialization.get("explicit_c_matrix_count") == 0
                and primary_materialization.get("explicit_d_matrix_count") == 0
            ),
            "e0_oracle_c_d_materialization_one": (
                oracle_materialization.get("matrix_free_dtn") is False
                and oracle_materialization.get("explicit_c_matrix_count") == 1
                and oracle_materialization.get("explicit_d_matrix_count") == 1
            ),
            "e0_profiles_separate": (
                materialization.get("profiles_separate") is True
                if isinstance(materialization, dict)
                else False
            ),
            "e0_no_factorization_or_solve_event": (
                not _factorization_stage_seen(events) and not _solve_stage_seen(events)
            ),
            "e0_ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "e0_no_official_result": (solver_summary.get("official_result") is False),
            "e0_no_ksp_solve": (
                solver_summary.get("matrix_diagnostics_assemble_only") is True
                and solver_summary.get("postprocess_skipped") is True
            ),
            "no_swap": no_swap,
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "pass": not failures,
            "checks": checks,
            "failures": failures,
            "task035d_case097_solver_gate": None,
        }
    if args.task037_f3_full or args.task037_f3_screen is not None:
        core_audit = task037_f3_core_audit or {}
        expected_iterations = _task037_f3_iterations(args)
        screen_checks = _task037_f3_screen_gate(
            core_audit,
            expected_iterations,
            solver_summary.get("elapsed_seconds"),
            expected_factor_free_steps=(
                int(args.task037_m4_factor_free_local_steps)
                if m4_factor_free_profile or m4_optimized_schwarz_profile
                else None
            ),
            expected_factor_free_variant=(
                "ras" if m4_optimized_schwarz_profile else None
            ),
        )
        core_profile = core_audit.get("solver_profile")
        core_released = core_audit.get("assembled_matrix_released_before_solve")
        reason = solver_summary.get("ksp_converged_reason")
        residual = solver_summary.get("linear_system_relative_residual")
        positive = isinstance(reason, (int, float)) and reason > 0
        negative = isinstance(reason, (int, float)) and reason < 0
        prefix = "full_" if args.task037_f3_full else ""
        checks = {
            **common,
            **{
                f"task037_f3_{prefix}{name}": passed
                for name, passed in screen_checks.items()
            },
            "external_linear_solver_port": (
                solver_summary.get("external_linear_solver_port") is True
            ),
            "external_no_global_factor": (
                solver_summary.get("external_no_global_factor") is True
            ),
            "full_fe_residual_scale": _finite_number_le(
                residual, 1.0e-6 if positive else 10.0
            ),
            "reason_output_gate": positive
            or (
                negative
                and solver_summary.get("official_result") is False
                and solver_summary.get("postprocess_skipped") is True
            ),
            "no_swap": no_swap,
        }
        if args.task037_f3_full:
            checks.update(
                {
                    "positive_official_postprocess": (
                        positive
                        and solver_summary.get("official_result") is True
                        and solver_summary.get("postprocess_skipped") is False
                    ),
                    "external_rta_gate_pass": (
                        solver_summary.get("external_rta_gate_pass") is True
                    ),
                }
            )
        if args.task037_f5b_released_profile:
            checks.update(
                {
                    "f5b_core_release_profile": (
                        core_profile
                        == "assembled_setup_then_static_local_schur_matrix_free_solve"
                        and core_released is True
                    ),
                    "f5b_summary_release_profile": (
                        solver_summary.get("external_solver_profile") == core_profile
                        and solver_summary.get(
                            "external_assembled_matrix_released_before_solve"
                        )
                        is True
                    ),
                }
            )
        if m3a_profile:
            partition = core_audit.get("partition_audit") or {}
            smoother = core_audit.get("smoother_diagnostics") or {}
            inventory = core_audit.get("no_global_factor_inventory") or {}
            resource = resource_summary if isinstance(resource_summary, dict) else {}
            memory_authority_gib = resource.get("memory_authority_gib")
            checks.update(
                {
                    "m3a_core_profile": (
                        core_profile
                        == "never_materialized_owner_local_overlap0125_partition"
                    ),
                    "m3a_core_no_assembled_release": core_released is False,
                    "m3a_core_no_global_A": (
                        core_audit.get("global_A_materialized") is False
                    ),
                    "m3a_core_no_global_F": (
                        core_audit.get("global_F_materialized") is False
                    ),
                    "m3a_partition_weighted_0125": (
                        partition.get("matrix_materialized") is False
                        and partition.get("num_slabs") == 16
                        and partition.get("overlap_fraction") == 0.125
                        and partition.get("interpolation") == "partition"
                        and smoother.get("interpolation") == "partition"
                        and isinstance(
                            partition.get("partition_weight_sum_error"),
                            (int, float),
                        )
                        and float(partition["partition_weight_sum_error"]) <= 1.0e-12
                    ),
                    "m3a_two_color_factor_only_ilu": (
                        smoother.get("assembly_order") == "two_color"
                        and smoother.get("smoother_iterations") == 2
                        and smoother.get("smoother_ksp_type") == "gmres"
                        and smoother.get("factor_only_storage") is True
                        and all(
                            kind == "ilu"
                            for kind in smoother.get("local_solver_types", ())
                        )
                    ),
                    "m3a_no_global_direct_factor": (
                        inventory.get("global_direct_factor_count") == 0
                        and inventory.get("global_schur_matrix_materialized") is False
                    ),
                    "m3a_stored_factor_nnz_reduced": (
                        isinstance(smoother.get("global_stored_factor_nnz"), int)
                        and smoother["global_stored_factor_nnz"] < 103336560
                    ),
                    "m3a_memory_authority_le_10_30_gib": (
                        _finite_number_le(memory_authority_gib, 10.30)
                    ),
                    "m3a_summary_action_only": (
                        condensation.get("action_only_setup") is True
                    ),
                    "m3a_summary_no_global_A": (
                        condensation.get("global_A_materialized") is False
                    ),
                    "m3a_summary_no_global_F": (
                        condensation.get("global_F_materialized") is False
                    ),
                    "m3a_summary_profile": (
                        solver_summary.get("external_solver_profile") == core_profile
                    ),
                }
            )
        elif m2c_profile:
            partition = core_audit.get("partition_audit") or {}
            smoother = core_audit.get("smoother_diagnostics") or {}
            inventory = core_audit.get("no_global_factor_inventory") or {}
            resource = resource_summary if isinstance(resource_summary, dict) else {}
            memory_authority_gib = resource.get("memory_authority_gib")
            checks.update(
                {
                    "m2c_core_profile": (
                        core_profile == "never_materialized_owner_local"
                    ),
                    "m2c_core_no_assembled_release": (core_released is False),
                    "m2c_core_no_global_A": (
                        core_audit.get("global_A_materialized") is False
                    ),
                    "m2c_core_no_global_F": (
                        core_audit.get("global_F_materialized") is False
                    ),
                    "m2c_partition_not_materialized": (
                        partition.get("matrix_materialized") is False
                    ),
                    "m2c_two_step_two_color_ilu": (
                        smoother.get("assembly_order") == "two_color"
                        and smoother.get("smoother_iterations") == 2
                        and smoother.get("smoother_ksp_type") == "gmres"
                        and smoother.get("factor_only_storage") is True
                    ),
                    "m2c_no_global_factor": (
                        inventory.get("global_direct_factor_count") == 0
                        and inventory.get("global_schur_matrix_materialized") is False
                    ),
                    "m2c_memory_authority_le_10_30_gib": (
                        _finite_number_le(memory_authority_gib, 10.30)
                    ),
                    "m2c_summary_action_only": (
                        condensation.get("action_only_setup") is True
                    ),
                    "m2c_summary_no_global_A": (
                        condensation.get("global_A_materialized") is False
                    ),
                    "m2c_summary_no_global_F": (
                        condensation.get("global_F_materialized") is False
                    ),
                    "m2c_summary_profile": (
                        solver_summary.get("external_solver_profile")
                        == core_profile
                        == "never_materialized_owner_local"
                    ),
                    "m2c_summary_no_assembled_release": (
                        solver_summary.get(
                            "external_assembled_matrix_released_before_solve"
                        )
                        is False
                    ),
                }
            )
        elif m4_factor_free_profile or m4_optimized_schwarz_profile:
            partition = core_audit.get("partition_audit") or {}
            inventory = core_audit.get("no_global_factor_inventory") or {}
            p2_pc = core_audit.get("smoother_diagnostics") or {}
            p2_setup = core_audit.get("p2_auxiliary_audit") or {}
            patch = p2_pc.get("factor_free_slab_patch") or {}
            factor_free_steps = int(args.task037_m4_factor_free_local_steps)
            expected_factor_free_profile = (
                "never_materialized_p2_factor_free_slab_ras_auxiliary"
                if m4_optimized_schwarz_profile
                else "never_materialized_p2_factor_free_slab_auxiliary"
            )
            resource = resource_summary if isinstance(resource_summary, dict) else {}
            memory_authority_gib = resource.get("memory_authority_gib")
            checks.update(
                {
                    "m4_factor_free_core_profile": (
                        core_profile == expected_factor_free_profile
                    ),
                    "m4_factor_free_core_no_assembled_release": (
                        core_released is False
                    ),
                    "m4_factor_free_core_no_global_A": (
                        core_audit.get("global_A_materialized") is False
                    ),
                    "m4_factor_free_core_no_global_F": (
                        core_audit.get("global_F_materialized") is False
                    ),
                    "m4_factor_free_partition": (
                        partition.get("p6_slab_matrix_materialized") is False
                        and partition.get("p6_slab_matrix_count") == 0
                        and partition.get("p6_factor_count") == 0
                        and partition.get("p6_factor_nnz") == 0
                        and partition.get("num_slabs") == 16
                        and partition.get("overlap_fraction") == 0.125
                        and partition.get("interpolation") == "partition"
                        and core_audit.get("candidate", {}).get("local_krylov_steps")
                        == factor_free_steps
                        and partition.get("local_krylov_steps") == factor_free_steps
                        and partition.get("local_inner_preconditioner") == "none"
                        and partition.get("outer_requires_fgmres") is True
                        and partition.get("global_A_materialized_by_pc") is False
                        and isinstance(
                            partition.get("partition_weight_sum_error"),
                            (int, float),
                        )
                        and float(partition["partition_weight_sum_error"]) <= 1.0e-12
                        and 0.0
                        < float(partition.get("partition_weight_min", 0.0))
                        <= float(partition.get("partition_weight_max", 0.0))
                        <= 1.0
                        and (
                            not m4_optimized_schwarz_profile
                            or (
                                args.task037_m4_optimized_schwarz
                                and partition.get("variant") == "ras"
                                and partition.get("correction_partition")
                                == "one_hot_ras"
                                and isinstance(
                                    partition.get("ras_core_sum_error"),
                                    (int, float),
                                )
                                and partition["ras_core_sum_error"] <= 1.0e-12
                                and int(partition.get("interface_row_count", 0)) > 0
                                and partition.get("interface_shift_mode")
                                == "shared_rows_only"
                                and partition.get("interface_shift_nonzero_rows")
                                == partition.get("interface_row_count")
                                and partition.get("noninterface_shift_nonzero_rows")
                                == 0
                            )
                        )
                    ),
                    "m4_factor_free_local_krylov": (
                        patch.get("profile") == "factor_free_local_slab_krylov"
                        and patch.get("num_slabs") == 16
                        and patch.get("local_krylov_steps") == factor_free_steps
                        and patch.get("local_inner_preconditioner") == "none"
                        and patch.get("outer_requires_fgmres") is True
                        and patch.get("p6_slab_matrix_materialized") is False
                        and patch.get("p6_slab_matrix_count") == 0
                        and patch.get("p6_factor_count") == 0
                        and patch.get("p6_factor_nnz") == 0
                        and patch.get("global_A_materialized_by_pc") is False
                        and patch.get("expected_action_calls")
                        == factor_free_steps * 16 * int(patch.get("apply_count", 0))
                        and patch.get("restricted_action_calls")
                        == patch.get("expected_action_calls")
                        and (
                            not m4_optimized_schwarz_profile
                            or (
                                patch.get("variant") == "ras"
                                and patch.get("correction_partition") == "one_hot_ras"
                                and patch.get("interface_shift_mode")
                                == "shared_rows_only"
                                and patch.get("interface_shift_nonzero_rows")
                                == patch.get("interface_row_count")
                                and int(patch.get("interface_row_count", 0)) > 0
                                and patch.get("noninterface_shift_nonzero_rows") == 0
                                and patch.get("partition_weighted_additive_schwarz")
                                is False
                            )
                        )
                    ),
                    "m4_factor_free_no_p6_factor": (
                        inventory.get("full_p6_global_direct_factor_count") == 0
                        and inventory.get("global_schur_matrix_materialized") is False
                        and inventory.get("p6_factor_count") == 0
                        and inventory.get("p6_factor_nnz") == 0
                        and inventory.get("p6_slab_matrix_count") == 0
                        and inventory.get("p2_distributed_mumps_factor_count") == 1
                        and inventory.get("wave_coarse_dense_lu_count") == 1
                    ),
                    "m4_factor_free_p2_mumps_factor": (
                        p2_pc.get("p2_factor_count") == 1
                        and p2_pc.get("p2_factor_solver_type") == "mumps"
                        and p2_pc.get("p2_matrix_materialized") is True
                        and p2_pc.get("p2_unshifted_matrix_retained") is False
                    ),
                    "m4_factor_free_operator_kinds": (
                        p2_setup.get("profile") == expected_factor_free_profile
                        and p2_setup.get("fine_operator_kind")
                        == "borrowed_p6_condensed_dtn_action"
                        and p2_setup.get("fine_schur_action_kind")
                        == "borrowed_p6_static_local_schur_action"
                        and p2_pc.get("profile") == expected_factor_free_profile
                    ),
                    "m4_factor_free_p2_apply_count": (
                        int(p2_pc.get("apply_count", 0)) > 0
                    ),
                    "m4_factor_free_wave_coarse_dimension": (
                        int((core_audit.get("coarse") or {}).get("dimension", -1)) == 75
                    ),
                    "m4_factor_free_memory_level1_le_10_30_gib": (
                        _finite_number_le(memory_authority_gib, 10.30)
                    ),
                    "m4_factor_free_summary_action_only": (
                        condensation.get("action_only_setup") is True
                    ),
                    "m4_factor_free_summary_no_global_A": (
                        condensation.get("global_A_materialized") is False
                    ),
                    "m4_factor_free_summary_no_global_F": (
                        condensation.get("global_F_materialized") is False
                    ),
                    "m4_factor_free_summary_profile": (
                        solver_summary.get("external_solver_profile")
                        == expected_factor_free_profile
                    ),
                }
            )
        elif m4_profile:
            partition = core_audit.get("partition_audit") or {}
            inventory = core_audit.get("no_global_factor_inventory") or {}
            p2_pc = core_audit.get("smoother_diagnostics") or {}
            resource = resource_summary if isinstance(resource_summary, dict) else {}
            memory_authority_gib = resource.get("memory_authority_gib")
            checks.update(
                {
                    "m4_core_profile": (
                        core_profile == "never_materialized_p2_auxiliary"
                    ),
                    "m4_core_no_assembled_release": core_released is False,
                    "m4_core_no_global_A": (
                        core_audit.get("global_A_materialized") is False
                    ),
                    "m4_core_no_global_F": (
                        core_audit.get("global_F_materialized") is False
                    ),
                    "m4_partition_no_p6_slab_matrix": (
                        partition.get("p6_slab_matrix_materialized") is False
                        and partition.get("p6_slab_matrix_count") == 0
                        and partition.get("p6_factor_count") == 0
                    ),
                    "m4_no_p6_factor": (
                        inventory.get("full_p6_global_direct_factor_count") == 0
                        and inventory.get("global_schur_matrix_materialized") is False
                        and inventory.get("p2_distributed_mumps_factor_count") == 1
                        and inventory.get("wave_coarse_dense_lu_count") == 1
                    ),
                    "m4_p2_mumps_factor": (
                        p2_pc.get("p2_factor_count") == 1
                        and p2_pc.get("p2_factor_solver_type") == "mumps"
                        and p2_pc.get("p2_matrix_materialized") is True
                        and p2_pc.get("p2_unshifted_matrix_retained") is False
                    ),
                    "m4_p2_apply_count": (int(p2_pc.get("apply_count", 0)) > 0),
                    "m4_wave_coarse_dimension": (
                        int((core_audit.get("coarse") or {}).get("dimension", -1)) == 75
                    ),
                    "m4_memory_level1_le_10_30_gib": (
                        _finite_number_le(memory_authority_gib, 10.30)
                    ),
                    "m4_memory_target_le_7_60_gib": (
                        _finite_number_le(memory_authority_gib, 7.60)
                    ),
                    "m4_summary_profile": (
                        solver_summary.get("external_solver_profile")
                        == "never_materialized_p2_auxiliary"
                    ),
                }
            )
    elif args.run_kind == "assembly-only":
        checks = {
            **common,
            "diagnostic_assemble_only_status": (
                solver_summary.get("case_status") == "diagnostic_assemble_only"
            ),
            "assemble_only_flag": (
                solver_summary.get("matrix_diagnostics_assemble_only") is True
            ),
            "no_factorization_or_solve_stage": not _factorization_stage_seen(events),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "no_swap": no_swap,
        }
    elif args.run_kind == "factorization-only":
        factor_inventory = solver_summary.get("stage4_dtn_factor_inventory")
        checks = {
            **common,
            "diagnostic_factorization_only_status": (
                solver_summary.get("case_status") == "diagnostic_factorization_only"
            ),
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_flag": (
                solver_summary.get("matrix_diagnostics_factorization_only") is True
            ),
            "factorization_stage_seen": _factorization_stage_seen(events),
            "solve_stage_not_seen": not _solve_stage_seen(events),
            "factor_inventory_recorded": isinstance(factor_inventory, dict),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "official_result_false": solver_summary.get("official_result") is False,
            "no_swap": no_swap,
        }
    else:
        residual = solver_summary.get("linear_system_relative_residual")
        checks = {
            **common,
            "completed_status": solver_summary.get("case_status") == "completed",
            "official_result": solver_summary.get("official_result") is True,
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_false": (
                solver_summary.get("matrix_diagnostics_factorization_only") is False
            ),
            "ksp_converged": solver_summary.get("ksp_converged") is True,
            "true_residual_le_1e-9": _finite_number_le(
                residual,
                1.0e-9,
            ),
            "reference_exported": (
                solver_summary.get("full3d_reference_exported") is True
            ),
            "swap_policy_satisfied": args.allow_swap or no_swap,
        }
    task035d_solver_gate = None
    if args.task035d_case097_gate:
        if args.task035d_candidate_id == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME:
            solver_gate_builder = task035d_case097_hp_factorial_bridge_solver_gate
        elif args.task035d_candidate_id == TASK035D_LEFT_GRATING_TOP_PLAN_NAME:
            solver_gate_builder = task035d_case097_left_grating_top_solver_gate
        elif args.task035d_candidate_id == TASK035D_COMBINED_HP_PLAN_NAME:
            solver_gate_builder = task035d_case097_combined_hp_solver_gate
        elif args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME:
            solver_gate_builder = task035d_case097_selective_face_solver_gate
        elif args.task035d_candidate_id == TASK035D_LOCAL_H_PLAN_NAME:
            solver_gate_builder = task035d_case097_local_h_solver_gate
        elif args.task035d_candidate_id == "sidewall_z0_guard_v1":
            solver_gate_builder = task035d_case097_sidewall_guard_solver_gate
        else:
            solver_gate_builder = task035d_case097_t30_solver_gate
        task035d_solver_gate = solver_gate_builder(solver_summary)
        checks.update(
            {
                f"task035d_solver_{name}": bool(passed)
                for name, passed in task035d_solver_gate["checks"].items()
            }
        )
        resource = resource_summary if isinstance(resource_summary, dict) else {}
        per_rank_smaps = resource.get("per_rank_smaps_rollup_peak_mb")
        per_rank_smaps = per_rank_smaps if isinstance(per_rank_smaps, dict) else {}
        expected_ranks = {str(rank) for rank in range(8)}
        checks.update(
            {
                "task035d_all_rank_smaps_readable": (
                    resource.get("max_worker_rank_smaps_readable_count") == 8.0
                    and isinstance(
                        resource.get("fully_readable_mpi8_smaps_sample_count"),
                        (int, float),
                    )
                    and float(resource["fully_readable_mpi8_smaps_sample_count"]) > 0.0
                    and set(per_rank_smaps) == expected_ranks
                ),
                "task035d_pss_uss_peaks_recorded": (
                    isinstance(
                        resource.get("max_simultaneous_worker_pss_mb"),
                        (int, float),
                    )
                    and float(resource["max_simultaneous_worker_pss_mb"]) > 0.0
                    and isinstance(
                        resource.get("max_simultaneous_worker_uss_mb"),
                        (int, float),
                    )
                    and float(resource["max_simultaneous_worker_uss_mb"]) > 0.0
                    and all(
                        isinstance(values, dict)
                        and isinstance(values.get("pss_mb"), (int, float))
                        and isinstance(values.get("uss_mb"), (int, float))
                        for values in per_rank_smaps.values()
                    )
                ),
                "task035d_cgroup_ledger_recorded": (
                    isinstance(
                        resource.get("max_container_cgroup_current_observed_mb"),
                        (int, float),
                    )
                    and isinstance(
                        resource.get("max_container_cgroup_peak_mb"),
                        (int, float),
                    )
                ),
                "task035d_zero_swap": no_swap,
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "task035d_case097_solver_gate": task035d_solver_gate,
    }


def _worker_command(args: argparse.Namespace, run_dir: Path) -> list[str]:
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
        "--worker",
        "--degree",
        str(args.degree),
        "--h-nm",
        str(args.h_nm),
        "--polarization-kind",
        args.polarization_kind,
        "--run-kind",
        args.run_kind,
        "--mpi-size",
        str(args.mpi_size),
        "--profile",
        args.profile,
        "--stage4-full3d-assembly-backend",
        args.stage4_full3d_assembly_backend,
        "--run-dir",
        str(run_dir),
    ]
    if args.task035c_p6_h10_gate:
        command.extend(
            (
                "--task035c-p6-h10-gate",
                "--task035c-p6-preflight-authority",
                str(args.task035c_p6_preflight_authority),
                "--task035c-p6-preflight-sha256",
                str(args.task035c_p6_preflight_sha256),
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
    if args.task037_e0_matrix_free_dtn_gate:
        command.append("--task037-e0-matrix-free-dtn-gate")
    if args.task037_e1_modal_basis_gate:
        command.append("--task037-e1-modal-basis-gate")
    if args.task037_e2_b4_snapshot_carrier:
        command.append("--task037-e2-b4-snapshot-carrier")
    if args.task037_e2_modal_capacity_gate:
        command.append("--task037-e2-modal-capacity-gate")
    if args.task037_f0_vector_observer:
        command.append("--task037-f0-vector-observer")
    if args.task037_f1_direct_trace_oracle is not None:
        command.extend(
            (
                "--task037-f1-direct-trace-oracle",
                str(args.task037_f1_direct_trace_oracle),
                "--task037-f1-direct-trace-sha256",
                str(args.task037_f1_direct_trace_sha256),
            )
        )
    if args.task037_f3_full:
        command.append("--task037-f3-full")
    elif args.task037_f3_screen is not None:
        command.extend(("--task037-f3-screen", str(args.task037_f3_screen)))
    if args.task037_f5b_released_profile:
        command.append("--task037-f5b-released-profile")
    if args.task037_m2c_never_materialized:
        command.append("--task037-m2c-never-materialized")
    if args.task037_m3a_overlap0125_partition:
        command.append("--task037-m3a-overlap0125-partition")
    if args.task037_m4_p2_auxiliary:
        command.append("--task037-m4-p2-auxiliary")
    if args.task037_m4_factor_free_slab:
        command.extend(
            (
                "--task037-m4-factor-free-slab",
                "--task037-m4-factor-free-local-steps",
                str(args.task037_m4_factor_free_local_steps),
            )
        )
    if args.task037_m4_b2_long_full:
        command.append("--task037-m4-b2-long-full")
    if args.task037_m4_optimized_schwarz:
        command.append("--task037-m4-optimized-schwarz")
    if args.task037_canonical_vector_export:
        command.append("--task037-canonical-vector-export")
    if args.task037_m0_lifecycle_audit:
        command.append("--task037-m0-lifecycle-audit")
    if args.task035d_case097_gate:
        plan_options = (
            (
                "--stage4-local-h-refinement-plan",
                str(args.stage4_local_h_refinement_plan),
                "--stage4-local-h-refinement-plan-sha256",
                str(args.stage4_local_h_refinement_plan_sha256),
            )
            if args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
            else (
                "--stage4-variable-p-cell-degree-plan",
                str(args.stage4_variable_p_cell_degree_plan),
                "--stage4-variable-p-cell-degree-plan-sha256",
                str(args.stage4_variable_p_cell_degree_plan_sha256),
            )
        )
        command.extend(
            (
                "--task035d-case097-gate",
                "--task035d-candidate-id",
                str(args.task035d_candidate_id),
                *plan_options,
                "--task035d-plan-authority",
                str(args.task035d_plan_authority),
                "--task035d-plan-authority-sha256",
                str(args.task035d_plan_authority_sha256),
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
        if args.task035d_nested_p_dwr_phase is not None:
            command.extend(
                (
                    "--task035d-nested-p-dwr-phase",
                    str(args.task035d_nested_p_dwr_phase),
                    "--task035d-significant-channel-authority",
                    str(args.task035d_significant_channel_authority),
                    "--task035d-significant-channel-authority-sha256",
                    str(args.task035d_significant_channel_authority_sha256),
                    "--task035d-nested-p-pair-authority",
                    str(args.task035d_nested_p_pair_authority),
                    "--task035d-nested-p-pair-authority-sha256",
                    str(args.task035d_nested_p_pair_authority_sha256),
                )
            )
            if args.task035d_nested_p_dwr_phase == "enriched-evaluate":
                command.extend(
                    (
                        "--task035d-coarse-snapshot-manifest",
                        str(args.task035d_coarse_snapshot_manifest),
                        "--task035d-coarse-snapshot-manifest-sha256",
                        str(args.task035d_coarse_snapshot_manifest_sha256),
                    )
                )
        elif args.task035d_selective_face_dwr_phase is not None:
            command.extend(
                (
                    "--task035d-selective-face-dwr-phase",
                    str(args.task035d_selective_face_dwr_phase),
                    "--task035d-significant-channel-authority",
                    str(args.task035d_significant_channel_authority),
                    "--task035d-significant-channel-authority-sha256",
                    str(args.task035d_significant_channel_authority_sha256),
                )
            )
            if args.task035d_selective_face_dwr_phase == "enriched-evaluate":
                command.extend(
                    (
                        "--task035d-selective-face-coarse-manifest",
                        str(args.task035d_selective_face_coarse_manifest),
                        ("--task035d-selective-face-coarse-manifest-sha256"),
                        str(args.task035d_selective_face_coarse_manifest_sha256),
                    )
                )
    if (
        args.parent_launch_descriptor is not None
        and args.parent_launch_descriptor_sha256 is not None
    ):
        command.extend(
            (
                "--parent-launch-descriptor",
                str(args.parent_launch_descriptor),
                "--parent-launch-descriptor-sha256",
                str(args.parent_launch_descriptor_sha256),
            )
        )
    return command


def _run_parent(args: argparse.Namespace) -> int:
    if args.mpi_size < 1:
        raise SystemExit("--mpi-size must be positive.")
    if args.poll_interval < 0.05:
        raise SystemExit("--poll-interval must be at least 0.05 seconds.")
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task034 effective WSL memory limit is unreadable.")
    if args.warning_gib is None:
        args.warning_gib = float(effective["warning_bytes"]) / GIB
    if args.terminate_gib is None:
        args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if args.warning_gib <= 0 or args.terminate_gib <= args.warning_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive.")
    if args.run_kind != "full-solve" and args.allow_swap:
        raise SystemExit(
            "assembly-only and factorization-only calibration forbid --allow-swap."
        )
    p4_gate = _validate_p4_gate(args)
    task035c_p6_gate = _validate_task035c_p6_preflight(args)
    task035d_case097_gate = _validate_task035d_case097_plan(args)
    task035d_nested_p_gate = _validate_task035d_nested_p_inputs(args)
    task035d_selective_face_gate = _validate_task035d_selective_face_inputs(args)
    source_before = _source_provenance(args)
    if (
        args.task035d_case097_gate
        or args.task037_f3_screen is not None
        or args.task037_f3_full
        or args.task037_canonical_vector_export
        or args.task037_e0_matrix_free_dtn_gate
        or args.task037_e1_modal_basis_gate
        or args.task037_e2_b4_snapshot_carrier
        or args.task037_e2_modal_capacity_gate
    ):
        task035d_status_before = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
        if task035d_status_before:
            raise SystemExit(
                "Task035d/Task37 F3/E0 formal PDE requires an actually clean "
                "source tree; commit the runner/checker and evidence before "
                "launch."
            )
    environment_before = _resource_snapshot()
    if environment_before["host_available_bytes"] is None:
        raise SystemExit("Readable WSL MemAvailable is required.")
    if environment_before["wsl_total_bytes"] is None:
        raise SystemExit("Readable WSL MemTotal is required.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / f"p{args.degree}_h{args.h_nm:g}_pol{args.polarization_kind}_{args.run_kind}_mpi{args.mpi_size}_{timestamp}"
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    args.run_dir = run_dir
    parent_launch_token = secrets.token_hex(32)
    parent_launch_descriptor = run_dir / "parent_launch_descriptor.json"
    parent_launch_payload = {
        "schema_version": "task033.watchdog-parent-launch.v1",
        "token_sha256": hashlib.sha256(parent_launch_token.encode("ascii")).hexdigest(),
        "parent_process": {
            **_linux_process_identity(os.getpid()),
            "role": "resource_watchdog_parent",
        },
        "worker_contract": _worker_launch_contract(args),
    }
    parent_launch_descriptor.write_text(
        json.dumps(
            parent_launch_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    args.parent_launch_descriptor = parent_launch_descriptor
    args.parent_launch_descriptor_sha256 = _sha256(parent_launch_descriptor)
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = _worker_command(args, run_dir)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            _PARENT_LAUNCH_TOKEN_ENV: parent_launch_token,
        }
    )
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    terminated_for_authority_unreadable = False
    with stdout_path.open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            **worker_process_group_popen_kwargs(),
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            process_tree_mb = row.get("mpi_process_tree_rss_mb")
            process_tree_swap_mb = row.get("mpi_process_tree_swap_mb")
            cgroup_mb = (
                row.get("container_cgroup_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            cgroup_swap_mb = (
                row.get("container_swap_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            authority_readable = all(
                isinstance(value, (int, float))
                for value in (
                    process_tree_mb,
                    process_tree_swap_mb,
                    cgroup_mb,
                    cgroup_swap_mb,
                )
            )
            authority_gib = (
                None
                if not authority_readable
                else max(float(process_tree_mb), float(cgroup_mb)) / 1024.0
            )
            if authority_gib is not None:
                warning_triggered |= authority_gib >= args.warning_gib
            if process.poll() is None and not authority_readable:
                terminated_for_authority_unreadable = True
                terminate_process_tree(process)
            elif (
                process.poll() is None
                and authority_gib is not None
                and authority_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                terminate_process_tree(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                terminate_process_tree(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    solver_path = run_dir / "run_summary.json"
    solver_summary = (
        json.loads(solver_path.read_text(encoding="utf-8"))
        if solver_path.is_file()
        else {}
    )
    e1_audit_path = run_dir / "task037_e1_modal_basis_audit.json"
    e1_audit_expected = bool(
        args.task037_e1_modal_basis_gate
        or args.task037_e2_modal_capacity_gate
    )
    if e1_audit_expected:
        try:
            e1_audit = json.loads(e1_audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            e1_audit = {}
        if not isinstance(e1_audit, dict):
            e1_audit = {}
    else:
        e1_audit = None
    e2_audit_path = (
        run_dir / "task037_e2_modal_capacity_audit.json"
        if args.task037_e2_modal_capacity_gate
        else run_dir / "task037_e2_b4_snapshot_audit.json"
    )
    if (
        args.task037_e2_b4_snapshot_carrier
        or args.task037_e2_modal_capacity_gate
    ):
        try:
            e2_audit = json.loads(e2_audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            e2_audit = {}
        if not isinstance(e2_audit, dict):
            e2_audit = {}
    else:
        e2_audit = None
    task037_f3_core_audit = None
    task037_f3_core_audit_path = run_dir / "task037_f3_core_audit.json"
    if args.task037_f3_screen is not None or args.task037_f3_full:
        try:
            task037_f3_core_audit = json.loads(
                task037_f3_core_audit_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            task037_f3_core_audit = {}
    dtn_orders_path = run_dir / "dtn_port_diffraction_orders_3d.json"
    field_shard_paths = [
        run_dir / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
        for rank in range(args.mpi_size)
    ]
    field_shard_authority = [
        {
            "rank": rank,
            "path": _path_from_root(path),
            "sha256": _sha256(path),
        }
        for rank, path in enumerate(field_shard_paths)
    ]
    events = _read_progress_events(progress_path)
    sampler = _sampler_summary(rows)
    sampler["poll_interval_seconds"] = args.poll_interval
    no_swap = bool(
        sampler["max_process_tree_swap_mb"] == 0.0
        and (
            not sampler["dedicated_job_cgroup_observed"]
            or sampler["max_container_swap_current_mb"] == 0.0
        )
    )
    qualification = _qualify(
        args=args,
        solver_summary=solver_summary,
        events=events,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        terminated_for_authority_unreadable=terminated_for_authority_unreadable,
        no_swap=no_swap,
        observed_worker_rank_count=sampler["max_observed_worker_rank_count"],
        resource_summary=sampler,
        task037_f3_core_audit=task037_f3_core_audit,
        task037_e1_audit=e1_audit,
        task037_e2_audit=e2_audit,
    )
    task035d_nested_p_evidence = None
    task035d_selective_face_evidence = None
    task035d_selective_face_controlled_negative = False
    if args.task035d_case097_gate:
        raw_artifact_checks = {
            "task035d_solver_summary_hash_bound": (_sha256(solver_path) is not None),
            "task035d_timeline_hash_bound": (_sha256(timeline_path) is not None),
            "task035d_progress_hash_bound": (_sha256(progress_path) is not None),
            "task035d_stdout_hash_bound": (_sha256(stdout_path) is not None),
            "task035d_dtn_orders_hash_bound": (_sha256(dtn_orders_path) is not None),
            "task035d_eight_field_shards_hash_bound": (
                len(field_shard_authority) == 8
                and all(
                    authority["sha256"] is not None
                    for authority in field_shard_authority
                )
            ),
        }
        if args.task035d_nested_p_dwr_phase == "coarse-snapshot":
            nested_path = run_dir / "nested_p_snapshot" / "manifest.json"
            try:
                nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                nested_payload = {}
            if not isinstance(nested_payload, dict):
                nested_payload = {}
            nested_shards = nested_payload.get("shards", ())
            nested_primal_gate = nested_payload.get("primal_residual_gate", {})
            nested_candidate = nested_payload.get("candidate", {})
            nested_trace = nested_payload.get("same_trace_identity", {})
            nested_checks = {
                "task035d_nested_p_coarse_manifest": (
                    _sha256(nested_path) is not None
                    and nested_payload.get("schema_version")
                    == ("task035d.variable-p-nested-coarse-snapshot.v1")
                    and nested_payload.get("pass") is True
                    and nested_payload.get("role") == "coarse_B"
                ),
                "task035d_nested_p_coarse_source": (
                    nested_candidate.get("source_sha") == args.verified_clean_sha
                ),
                "task035d_nested_p_coarse_candidate": (
                    nested_candidate.get("candidate_id")
                    == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
                    and nested_candidate.get("plan_file_sha256")
                    == args.stage4_local_h_refinement_plan_sha256
                    and nested_candidate.get("cell_interior_degree_counts")
                    == {"5": 32, "6": 102}
                    and nested_candidate.get("actual_full3d_equivalent_active_fe_dofs")
                    == 76_205
                ),
                "task035d_nested_p_coarse_trace_identity": (
                    nested_trace.get("mpi_size") == 8
                    and nested_trace.get("independent_trace_rows") == 18_390
                    and nested_trace.get("auxiliary_rows") == 80
                    and nested_trace.get("matrix_rows") == 18_470
                ),
                "task035d_nested_p_coarse_channel_authority": (
                    nested_payload.get("significant_channel_authority", {}).get(
                        "sha256"
                    )
                    == args.task035d_significant_channel_authority_sha256
                ),
                "task035d_nested_p_coarse_port_content": (
                    nested_payload.get("port_operator_audit", {}).get("pass") is True
                    and isinstance(
                        nested_payload.get("port_operator_audit", {}).get(
                            "external_operator_content_sha256"
                        ),
                        str,
                    )
                    and isinstance(
                        nested_payload.get("port_operator_audit", {}).get(
                            "external_rhs_content_sha256"
                        ),
                        str,
                    )
                ),
                "task035d_nested_p_coarse_primal_residual": (
                    nested_primal_gate.get("pass") is True
                    and len(nested_primal_gate.get("checks", {})) == 4
                    and all(nested_primal_gate.get("checks", {}).values())
                    and _finite_number_le(
                        nested_payload.get("vector_identity", {}).get(
                            "relative_residual"
                        ),
                        1.0e-9,
                    )
                    and _finite_number_le(
                        nested_payload.get("full_active_residual", {}).get(
                            "linear_system_relative_residual"
                        ),
                        1.0e-9,
                    )
                ),
                "task035d_nested_p_eight_hash_bound_shards": (
                    len(nested_shards) == 8
                    and all(
                        _sha256(nested_path.parent / str(shard["path"]))
                        == shard.get("sha256")
                        for shard in nested_shards
                    )
                ),
            }
            task035d_nested_p_evidence = {
                "phase": "coarse-snapshot",
                "path": _path_from_root(nested_path),
                "sha256": _sha256(nested_path),
                "payload": nested_payload,
            }
            raw_artifact_checks.update(nested_checks)
        elif args.task035d_nested_p_dwr_phase == "enriched-evaluate":
            nested_path = run_dir / "nested_p_dwr_report.json"
            try:
                nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                nested_payload = {}
            if not isinstance(nested_payload, dict):
                nested_payload = {}
            goal_dwr = nested_payload.get("goal_dwr", {})
            basis = nested_payload.get(
                "unit_channel_adjoint_basis",
                {},
            )
            primal_endpoints = nested_payload.get("primal_endpoints", {})
            coarse_endpoint_gate = primal_endpoints.get("coarse_residual_gate", {})
            enriched_endpoint_gate = primal_endpoints.get("enriched_residual_gate", {})
            basis_channels = basis.get("channels", {})
            basis_goals = basis.get("goals", {})
            try:
                channel_authority_payload = json.loads(
                    args.task035d_significant_channel_authority.read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, json.JSONDecodeError):
                channel_authority_payload = {}
            independent_checker_gate = task035d_nested_p_dwr_report_gate(
                nested_payload,
                channel_authority_payload,
            )
            nested_checks = {
                "task035d_nested_p_dwr_report": (
                    _sha256(nested_path) is not None
                    and nested_payload.get("schema_version")
                    == "task035d.variable-p-nested-live-dwr.v1"
                    and nested_payload.get("pass") is True
                ),
                "task035d_nested_p_endpoint_identity": (
                    nested_payload.get("enriched_candidate", {}).get("candidate_id")
                    == TASK035D_LOCAL_H_PLAN_NAME
                    and nested_payload.get("enriched_candidate", {}).get("source_sha")
                    == args.verified_clean_sha
                    and nested_payload.get("enriched_candidate", {}).get(
                        "plan_file_sha256"
                    )
                    == args.stage4_local_h_refinement_plan_sha256
                    and nested_payload.get("coarse_snapshot", {}).get("manifest_sha256")
                    == args.task035d_coarse_snapshot_manifest_sha256
                    and nested_payload.get("significant_channel_authority", {}).get(
                        "sha256"
                    )
                    == args.task035d_significant_channel_authority_sha256
                ),
                "task035d_nested_p_primal_endpoint_residuals": (
                    coarse_endpoint_gate.get("pass") is True
                    and enriched_endpoint_gate.get("pass") is True
                    and all(coarse_endpoint_gate.get("checks", {}).values())
                    and all(enriched_endpoint_gate.get("checks", {}).values())
                    and _finite_number_le(
                        primal_endpoints.get("coarse_relative_residual"),
                        1.0e-9,
                    )
                    and _finite_number_le(
                        primal_endpoints.get("enriched_relative_residual"),
                        1.0e-9,
                    )
                ),
                "task035d_nested_p_residual_partition": (
                    nested_payload.get("residual_partition", {}).get("pass") is True
                ),
                "task035d_nested_p_twelve_unit_adjoints": (
                    basis.get("pass") is True
                    and basis.get("unit_adjoint_solve_count") == 12
                    and basis.get("physical_channel_count") == 12
                    and len(basis_channels) == 12
                    and all(
                        channel.get("pass") is True
                        and _finite_number_le(
                            channel.get("adjoint_residual", {}).get(
                                "relative_residual"
                            ),
                            1.0e-9,
                        )
                        for channel in basis_channels.values()
                    )
                ),
                "task035d_nested_p_36_goal_closure": (
                    goal_dwr.get("pass") is True
                    and goal_dwr.get("passed_real_goal_count") == 36
                    and goal_dwr.get("power_goal_pass_count") == 12
                    and goal_dwr.get("complex_amplitude_component_goal_pass_count")
                    == 24
                    and len(goal_dwr.get("goals", {})) == 36
                    and all(
                        goal.get("pass") is True
                        for goal in goal_dwr.get("goals", {}).values()
                    )
                    and len(basis_goals) == 36
                    and all(
                        goal.get("pass") is True
                        and _finite_number_le(
                            goal.get("scaled_adjoint_residual", {}).get(
                                "relative_residual"
                            ),
                            1.0e-9,
                        )
                        for goal in basis_goals.values()
                    )
                    and nested_payload.get("significant_channel_authority", {}).get(
                        "selected_goal_set_complete_by_frozen_authority"
                    )
                    is True
                ),
                "task035d_nested_p_same_trace_only": (
                    nested_payload.get("same_trace_only") is True
                    and nested_payload.get("cross_trace_primal_prolongation_used")
                    is False
                ),
                "task035d_nested_p_independent_checker": (
                    independent_checker_gate["pass"] is True
                ),
            }
            task035d_nested_p_evidence = {
                "phase": "enriched-evaluate",
                "path": _path_from_root(nested_path),
                "sha256": _sha256(nested_path),
                "payload": nested_payload,
                "independent_checker": independent_checker_gate,
            }
            raw_artifact_checks.update(nested_checks)
        if args.task035d_selective_face_dwr_phase == "coarse-snapshot":
            selective_path = run_dir / "selective_face_snapshot" / "manifest.json"
            try:
                selective_payload = json.loads(
                    selective_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                selective_payload = {}
            if not isinstance(selective_payload, dict):
                selective_payload = {}
            arrays_path = selective_path.parent / str(
                selective_payload.get("arrays", {}).get("path", "")
            )
            arrays_sha = (
                _sha256(arrays_path)
                if arrays_path.parent == selective_path.parent and arrays_path.is_file()
                else None
            )
            selective_gate = task035d_selective_face_coarse_snapshot_gate(
                selective_payload,
                expected_source_sha=str(args.verified_clean_sha),
                expected_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                expected_significant_channel_authority_sha256=(
                    str(args.task035d_significant_channel_authority_sha256)
                ),
                observed_arrays_sha256=arrays_sha,
            )
            selective_checks = {
                "task035d_selective_face_coarse_manifest": (
                    _sha256(selective_path) is not None
                ),
                "task035d_selective_face_coarse_arrays": (arrays_sha is not None),
                "task035d_selective_face_coarse_independent_gate": (
                    selective_gate["pass"] is True
                ),
            }
            task035d_selective_face_evidence = {
                "phase": "coarse-snapshot",
                "path": _path_from_root(selective_path),
                "sha256": _sha256(selective_path),
                "arrays_path": _path_from_root(arrays_path),
                "arrays_sha256": arrays_sha,
                "payload": selective_payload,
                "independent_checker": selective_gate,
            }
            raw_artifact_checks.update(selective_checks)
        elif args.task035d_selective_face_dwr_phase == "enriched-evaluate":
            selective_path = run_dir / "selective_face_dwr_report.json"
            try:
                selective_payload = json.loads(
                    selective_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                selective_payload = {}
            if not isinstance(selective_payload, dict):
                selective_payload = {}
            try:
                selective_authority_payload = json.loads(
                    args.task035d_significant_channel_authority.read_text(
                        encoding="utf-8"
                    )
                )
            except (AttributeError, OSError, json.JSONDecodeError):
                selective_authority_payload = {}
            if not isinstance(selective_authority_payload, dict):
                selective_authority_payload = {}
            try:
                selective_coarse_endpoint = load_selective_face_coarse_endpoint(
                    args.task035d_selective_face_coarse_manifest,
                    expected_manifest_sha256=str(
                        args.task035d_selective_face_coarse_manifest_sha256
                    ),
                )
            except (OSError, TypeError, ValueError):
                selective_coarse_endpoint = {}
            selective_gate = task035d_selective_face_dwr_report_gate(
                selective_payload,
                selective_authority_payload,
                selective_coarse_endpoint,
                expected_source_sha=str(args.verified_clean_sha),
                expected_coarse_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                expected_enriched_plan_sha256=str(
                    args.stage4_local_h_refinement_plan_sha256
                ),
                expected_coarse_manifest_sha256=str(
                    args.task035d_selective_face_coarse_manifest_sha256
                ),
                expected_significant_channel_authority_sha256=str(
                    args.task035d_significant_channel_authority_sha256
                ),
            )
            task035d_selective_face_controlled_negative = (
                _task035d_selective_face_controlled_negative(
                    selective_payload,
                    report_sha256=_sha256(selective_path),
                )
            )
            selective_checks = {
                "task035d_selective_face_dwr_report": (
                    _sha256(selective_path) is not None
                ),
                "task035d_selective_face_dwr_independent_checker": (
                    selective_gate["pass"] is True
                ),
            }
            task035d_selective_face_evidence = {
                "phase": "enriched-evaluate",
                "path": _path_from_root(selective_path),
                "sha256": _sha256(selective_path),
                "payload": selective_payload,
                "independent_checker": selective_gate,
            }
            raw_artifact_checks.update(selective_checks)
        qualification["checks"].update(raw_artifact_checks)
        qualification["failures"].extend(
            name for name, passed in raw_artifact_checks.items() if not passed
        )
        qualification["pass"] = not qualification["failures"]
    source_head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = bool(
        source_head_after == source_before["commit_sha"] and not source_status_after
    )
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    m3a_status = _task037_m3a_status(args, qualification)
    m4_b2_long_full_status = _task037_m4_b2_long_full_status(args, qualification)
    m4_factor_free_status = _task037_m4_factor_free_status(args, qualification)
    m4_optimized_schwarz_status = _task037_m4_optimized_schwarz_status(
        args, qualification
    )
    status = (
        "task037_e2_modal_capacity_gate_pass"
        if qualification["pass"] and args.task037_e2_modal_capacity_gate
        else "task037_e2_modal_capacity_gate_not_pass"
        if args.task037_e2_modal_capacity_gate
        else
        "task037_e2_b4_snapshot_carrier_pass"
        if qualification["pass"] and args.task037_e2_b4_snapshot_carrier
        else "task037_e2_b4_snapshot_carrier_not_pass"
        if args.task037_e2_b4_snapshot_carrier
        else "task037_e1_modal_basis_gate_pass"
        if qualification["pass"] and args.task037_e1_modal_basis_gate
        else "task037_e1_modal_basis_gate_not_pass"
        if args.task037_e1_modal_basis_gate
        else "task037_e0_matrix_free_dtn_gate_pass"
        if qualification["pass"] and args.task037_e0_matrix_free_dtn_gate
        else "task037_e0_matrix_free_dtn_gate_not_pass"
        if args.task037_e0_matrix_free_dtn_gate
        else m4_b2_long_full_status
        if m4_b2_long_full_status is not None
        else m4_optimized_schwarz_status
        if m4_optimized_schwarz_status is not None
        else m4_factor_free_status
        if m4_factor_free_status is not None
        else f"task037_m4_p2_auxiliary_{args.task037_f3_screen}_screen_pass"
        if qualification["pass"] and args.task037_m4_p2_auxiliary
        else f"task037_m4_p2_auxiliary_{args.task037_f3_screen}_screen_not_pass"
        if args.task037_m4_p2_auxiliary
        else m3a_status
        if m3a_status is not None
        else "task037_m2c_never_materialized_screen_pass"
        if qualification["pass"] and args.task037_m2c_never_materialized
        else "task037_m2c_never_materialized_screen_not_pass"
        if args.task037_m2c_never_materialized
        else "task037_f5b_matrix_free_full_pass"
        if qualification["pass"] and args.task037_f5b_released_profile
        else "task037_f5b_matrix_free_full_not_pass"
        if args.task037_f5b_released_profile
        else "task037_f3_assembled_full_pass"
        if qualification["pass"] and args.task037_f3_full
        else "task037_f3_assembled_full_not_pass"
        if args.task037_f3_full
        else f"task037_f3_{args.task037_f3_screen}_screen_pass"
        if qualification["pass"] and args.task037_f3_screen is not None
        else f"task037_f3_{args.task037_f3_screen}_screen_not_pass"
        if args.task037_f3_screen is not None
        else "assembly_calibration_pass"
        if qualification["pass"] and args.run_kind == "assembly-only"
        else "factorization_calibration_pass"
        if qualification["pass"] and args.run_kind == "factorization-only"
        else "task035d_nested_p_coarse_snapshot_pass"
        if (
            qualification["pass"]
            and args.task035d_nested_p_dwr_phase == "coarse-snapshot"
        )
        else "task035d_nested_p_live_dwr_pass"
        if (
            qualification["pass"]
            and args.task035d_nested_p_dwr_phase == "enriched-evaluate"
        )
        else "task035d_selective_face_coarse_snapshot_pass"
        if (
            qualification["pass"]
            and args.task035d_selective_face_dwr_phase == "coarse-snapshot"
        )
        else "task035d_selective_face_live_dwr_pass"
        if (
            qualification["pass"]
            and args.task035d_selective_face_dwr_phase == "enriched-evaluate"
        )
        else "task035d_selective_face_live_dwr_controlled_negative"
        if (
            args.task035d_selective_face_dwr_phase == "enriched-evaluate"
            and task035d_selective_face_controlled_negative
        )
        else "task035d_candidate_numerical_pass"
        if qualification["pass"] and args.task035d_case097_gate
        else "full3d_reference_pass"
        if qualification["pass"]
        else "formal_not_pass"
    )
    matrix = solver_summary.get("matrix_stats") or {}
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "degree": args.degree,
        "h_nm": args.h_nm,
        "polarization_kind": args.polarization_kind,
        "run_kind": args.run_kind,
        "mpi_size": args.mpi_size,
        "profile": args.profile,
        "stage4_full3d_assembly_backend_requested": (
            args.stage4_full3d_assembly_backend
        ),
        "stage4_full3d_assembly_backend_actual": solver_summary.get(
            "stage4_full3d_assembly_backend_actual"
        ),
        "command": command,
        "parent_launch_descriptor": {
            "path": _path_from_root(parent_launch_descriptor),
            "sha256": args.parent_launch_descriptor_sha256,
            "payload": parent_launch_payload,
            "secret_token_persisted": False,
        },
        "source": {
            **source_before,
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            "head_after_sha": source_head_after,
            "status_after": source_status_after,
            "stable_and_clean_after": source_stable,
        },
        "p4_prerequisite_gate": p4_gate,
        "task035c_p6_h10_preflight_gate": task035c_p6_gate,
        "task035d_case097_launch_gate": task035d_case097_gate,
        "task035d_nested_p_launch_gate": task035d_nested_p_gate,
        "task035d_selective_face_launch_gate": (task035d_selective_face_gate),
        "task037_m4_b2_long_full": bool(args.task037_m4_b2_long_full),
        "task035d_candidate_id": (
            args.task035d_candidate_id if args.task035d_case097_gate else None
        ),
        "task035d_accuracy_credit": (
            "pending_independent_12_channel_and_field_checker"
            if args.task035d_case097_gate
            else None
        ),
        "task035d_nested_p_dwr_phase": (args.task035d_nested_p_dwr_phase),
        "task035d_nested_p_evidence": task035d_nested_p_evidence,
        "task035d_selective_face_dwr_phase": (args.task035d_selective_face_dwr_phase),
        "task035d_selective_face_evidence": (task035d_selective_face_evidence),
        "task037_e0_matrix_free_dtn_gate": bool(args.task037_e0_matrix_free_dtn_gate),
        "task037_e0_matrix_free_dtn_probe_audit": solver_summary.get(
            "matrix_free_dtn_probe_audit"
        ),
        "task037_e1_modal_basis_gate": bool(args.task037_e1_modal_basis_gate),
        "task037_e1_modal_basis_executed_for_e2_capacity": bool(
            args.task037_e2_modal_capacity_gate
        ),
        "task037_e1_modal_basis_audit": (
            {
                "path": _path_from_root(e1_audit_path),
                "sha256": _sha256(e1_audit_path),
                "payload": e1_audit,
            }
            if e1_audit_expected
            else None
        ),
        "task037_e2_b4_snapshot_carrier": bool(
            args.task037_e2_b4_snapshot_carrier
        ),
        "task037_e2_b4_snapshot_admission": (
            _task037_e2_b4_admission(args)
            if args.task037_e2_b4_snapshot_carrier
            else None
        ),
        "task037_e2_b4_snapshot_audit": (
            {
                "path": _path_from_root(e2_audit_path),
                "sha256": _sha256(e2_audit_path),
                "payload": e2_audit,
            }
            if args.task037_e2_b4_snapshot_carrier
            else None
        ),
        "task037_e2_modal_capacity_gate": bool(
            args.task037_e2_modal_capacity_gate
        ),
        "task037_e2_modal_capacity_admission": (
            _task037_e2_modal_capacity_admission(args)
            if args.task037_e2_modal_capacity_gate
            else None
        ),
        "task037_e2_modal_capacity_audit": (
            {
                "path": _path_from_root(e2_audit_path),
                "sha256": _sha256(e2_audit_path),
                "payload": e2_audit,
            }
            if args.task037_e2_modal_capacity_gate
            else None
        ),
        "resource_policy": {
            "swap_allowed": args.allow_swap,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "termination_authority": (
                "max(process-tree RSS, dedicated job cgroup memory.current when present)"
            ),
            "timeout_seconds": args.timeout_seconds,
            "formal_no_swap_authority": "process-tree VmSwap plus dedicated job cgroup swap",
            "wsl_global_pswp_role": "diagnostic_only",
            "mumps_ooc_role": "explicit_scratch_profile_not_linux_swap",
            "effective_limit": effective,
        },
        "environment_before": environment_before,
        "environment_after": _resource_snapshot(),
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "terminated_for_authority_unreadable": (terminated_for_authority_unreadable),
        "no_swap": no_swap,
        "resource_authority": sampler,
        "calibration": {
            "exact_rows": matrix.get("matrix_rows"),
            "exact_assembled_nnz": matrix.get("matrix_nnz_used"),
            "matrix_petsc_memory_bytes": matrix.get("matrix_memory_bytes"),
            "matrix_payload_estimate_bytes": matrix.get("matrix_memory_estimate_bytes"),
            "num_nedelec_dofs": solver_summary.get("num_nedelec_dofs"),
            "num_auxiliary_dofs": solver_summary.get("stage4_dtn_num_auxiliary_dofs"),
            "floquet_constraint_rows": solver_summary.get("floquet_num_constraints"),
            "floquet_constraint_raw_map_nnz": solver_summary.get("floquet_raw_map_nnz"),
            "floquet_constraint_timings_seconds": solver_summary.get(
                "floquet_constraint_timings_seconds"
            ),
            "floquet_created_dense_boundary_square": solver_summary.get(
                "floquet_created_dense_boundary_square"
            ),
            "dtn_auxiliary_block_stats": solver_summary.get(
                "stage4_dtn_auxiliary_block_stats"
            ),
            "explicit_chac_constructed": solver_summary.get(
                "explicit_chac_constructed"
            ),
            "factorization_or_solve_stage_seen": _factorization_stage_seen(events),
        },
        "matrix_inventory": {
            "base": solver_summary.get("stage4_dtn_base_matrix_stats"),
            "augmented": solver_summary.get(
                "stage4_dtn_augmented_matrix_stats_after_finalize"
            ),
            "final": matrix,
            "constraint_transform": solver_summary.get("constraint_matrix_transform"),
        },
        "timings_seconds": solver_summary.get("timings_seconds"),
        "historical_peak_upper_bound_mb": _historical_peak_upper_bound(
            events, solver_summary
        ),
        "qualification": qualification,
        "return_code": return_code,
        "solver_summary_sha256": _sha256(solver_path),
        "timeline_sha256": _sha256(timeline_path),
        "progress_sha256": _sha256(progress_path),
        "stdout_sha256": _sha256(stdout_path),
        "dtn_orders_sha256": _sha256(dtn_orders_path),
        "field_shard_authority": field_shard_authority,
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "solver_summary": _path_from_root(solver_path),
            "timeline": _path_from_root(timeline_path),
            "progress": _path_from_root(progress_path),
            "stdout": _path_from_root(stdout_path),
            "dtn_orders": _path_from_root(dtn_orders_path),
            "field_shards": field_shard_authority,
            **(
                {
                    "task037_f3": {
                        "full": bool(args.task037_f3_full),
                        "b2_long_full": bool(args.task037_m4_b2_long_full),
                        "f5b_released_profile": bool(args.task037_f5b_released_profile),
                        "screen_iterations": args.task037_f3_screen,
                        "core_audit_path": _path_from_root(task037_f3_core_audit_path),
                        "core_audit_sha256": _sha256(task037_f3_core_audit_path),
                        "core_audit_payload": task037_f3_core_audit,
                        "residual_history_path": _path_from_root(
                            run_dir / "task037_f3_residual_history.jsonl"
                        ),
                        "residual_history_sha256": _sha256(
                            run_dir / "task037_f3_residual_history.jsonl"
                        ),
                    }
                }
                if args.task037_f3_screen is not None or args.task037_f3_full
                else {}
            ),
        },
        "solver_summary": solver_summary,
    }
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": status,
                "degree": args.degree,
                "h_nm": args.h_nm,
                "polarization_kind": args.polarization_kind,
                "run_kind": args.run_kind,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "combined_memory_swap_authority_gib": sampler[
                    "combined_memory_swap_authority_gib"
                ],
                "no_swap": no_swap,
                "record": _path_from_root(record_path),
                "failures": qualification["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if qualification["pass"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir.")
        _validate_worker_parent_launch(args)
        _revalidate_task035d_worker_inputs(args)
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
