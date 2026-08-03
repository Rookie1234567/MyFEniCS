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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "cases" / "091" / "task033_full3d"
)
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
GIB = 1024**3
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


def _task037_f0_solution_observer(run_dir: Path):
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
        if comm.rank != 0:
            return
        active_values = system_values[:active_rows]
        np.save(run_dir / "task037_active_trace_vector.npy", active_values)
        np.save(run_dir / "task037_recovered_full_fe_vector.npy", recovered_values)
        summary["task037_f0_vector_identity"] = {
            "active_trace": {
                **_task037_canonical_identity(
                    "task037.f0.active_trace",
                    active_values,
                ),
                "source": "linear_system.x prefix; raw=ignored run_dir",
            },
            "recovered_full_fe": {
                **_task037_canonical_identity(
                    "task037.f0.recovered_full_fe",
                    recovered_values,
                ),
                "source": "field.x.petsc_vec ownership order; raw=ignored run_dir",
            },
        }

    return observe


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
    if not args.task035d_case097_gate:
        return
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
            "Task035d worker source identity is not the clean parent-qualified commit."
        )


def _worker(args: argparse.Namespace) -> int:
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    observer = (
        _task037_f0_solution_observer(args.run_dir)
        if args.task037_f0_vector_observer
        else None
    )
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
        variable_p_live_observer=observer,
        variable_p_retain_local_schur_for_research=(retain_local_schur),
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
    if args.task037_f0_vector_observer and not (
        args.task035c_p6_h10_gate
        and args.mpi_size == 8
        and args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    ):
        parser.error(
            "--task037-f0-vector-observer requires the existing Task035c "
            "p6/h10 gate, full-solve, static backend, MPI8, and S scope."
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
) -> dict[str, Any]:
    matrix = solver_summary.get("matrix_stats") or {}
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
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
        ),
        "polarization_identity": (
            solver_summary.get("polarization_kind") == args.polarization_kind
        ),
    }
    if args.run_kind == "assembly-only":
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
    if args.task037_f0_vector_observer:
        command.append("--task037-f0-vector-observer")
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
    if args.task035d_case097_gate:
        task035d_status_before = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
        if task035d_status_before:
            raise SystemExit(
                "Task035d formal PDE requires an actually clean source tree; "
                "commit the runner/checker and evidence before launch."
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
    status = (
        "assembly_calibration_pass"
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
