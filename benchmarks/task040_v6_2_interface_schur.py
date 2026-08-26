"""Thin V6-2 full-interface Schur identity runner.

The runner is an opt-in research route.  It records only scalar and owner-local
metadata evidence; no numerical NPY packet is written and no full-side factor,
physical DtN block, or global numeric gather is permitted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_schur import (
    build_canonical_interface_layout,
    build_petsc_full_interface_schur_action,
    build_petsc_interface_schur_oracle,
    build_v6_cell_recovery_owner_group_rows,
)


V6_2_INTERFACE_SCHUR_FLAG = "--v6-2-interface-schur"
V6_2_INTERFACE_SCHUR_METHOD = "task040_v6_2_full_interface_schur"
V6_2_INTERFACE_SCHUR_SCHEMA = "task040.v6_2.full_interface_schur.v1"
V6_2_INTERFACE_SCHUR_PROFILE_ID = "task040.v6_2.h4.full_interface.v1"
V6_2_INTERFACE_LOWER_COUNT = 7560
V6_2_INTERFACE_UPPER_COUNT = 7560
V6_2_INTERFACE_JOINT_COUNT = (
    V6_2_INTERFACE_LOWER_COUNT + V6_2_INTERFACE_UPPER_COUNT
)
V6_2_ZERO_TOLERANCE = 1.0e-13
V6_2_ROUNDTRIP_TOLERANCE = 1.0e-11
V6_2_ACTION_TOLERANCE = 1.0e-10
V6_2_RESOURCE_HEADROOM_BYTES = 4 * 2**30
V6_2_MIN_DISK_FREE_BYTES = 20 * 2**30
V6_2_EXACT_QUALIFICATION_SOURCES = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)

__all__ = (
    "V6_2_INTERFACE_SCHUR_FLAG",
    "V6_2_INTERFACE_SCHUR_METHOD",
    "V6_2_INTERFACE_SCHUR_SCHEMA",
    "V6_2_INTERFACE_SCHUR_PROFILE_ID",
    "V6_2_INTERFACE_LOWER_COUNT",
    "V6_2_INTERFACE_UPPER_COUNT",
    "V6_2_INTERFACE_JOINT_COUNT",
    "V6_2_RESOURCE_HEADROOM_BYTES",
    "V6_2_MIN_DISK_FREE_BYTES",
    "V6_2_EXACT_QUALIFICATION_SOURCES",
    "build_v6_2_exact_qualification_plan",
    "run_v6_2_interface_schur",
)


def build_v6_2_exact_qualification_plan() -> dict[str, Any]:
    """Describe the post-identity qualification path without running it.

    This contract is emitted by the identity runner so a later formal run has
    one auditable sequence: the first two current-layout sources must pass
    before the remaining three are attempted.  It deliberately contains no
    numerical result and does not authorize a heavy run by itself.
    """

    return {
        "status": "designed_not_run",
        "source_order": list(V6_2_EXACT_QUALIFICATION_SOURCES),
        "rhs_layout": "current_canonical_active_keys_owner_local",
        "interface_rhs": "g=b_Gamma-A_GammaI*A_II^-1*b_I",
        "checkpoints": [16, 32, 64, 128],
        "conditional_checkpoints": [256, 512],
        "solution_recovery": (
            "x_I=A_II^-1*(b_I-A_I,Gamma*x_Gamma)"
        ),
        "full_residual": "independent_current_bare_F_mult",
        "first_two_gate": "each relative true residual <= 1e-9",
        "remaining_sources": "run only after first_two_gate",
        "one_cell_source_factor": "not_reexecuted",
        "full_side_exact_factor": "not_constructed_in_identity_runner",
        "frozen_owner_row_arrays": (
            "not_loaded; complex PETSc owner-order values, never row ids"
        ),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"V6-2 value is not JSON-safe: {type(value)!r}")


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = json.dumps(
        _json_safe(payload), sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _emit(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    stage: str,
    **detail: Any,
) -> None:
    if callback is not None:
        callback(stage, detail)


def _collective_error(
    comm: MPI.Intracomm,
    stage: str,
    local_error: str | None,
) -> None:
    errors = comm.allgather(local_error)
    first = next(
        ((rank, error) for rank, error in enumerate(errors) if error is not None),
        None,
    )
    if first is not None:
        rank, error = first
        raise RuntimeError(f"V6-2 {stage} failed on rank {rank}: {error}")


def _global_max(comm: MPI.Intracomm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _local_mapping_sha256(mapping: Mapping[int, int]) -> str:
    encoded = json.dumps(
        [[int(row), int(position)] for row, position in sorted(mapping.items())],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _support_summary(
    comm: MPI.Intracomm,
    support: np.ndarray,
    *,
    global_count: int,
    global_hash: str,
) -> dict[str, Any]:
    local_hash = hashlib.sha256(
        np.ascontiguousarray(np.asarray(support, dtype=np.int64)).tobytes()
    ).hexdigest()
    return {
        "local_count": int(support.size),
        "local_sha256": local_hash,
        "global_count": int(global_count),
        "global_sha256": str(global_hash),
        "owner_local": True,
        "replicated": False,
        "numeric_allgather": False,
        "support_metadata_replicated": True,
        "rank_local_hashes": comm.allgather(local_hash),
    }


def _resource_preflight(
    comm: MPI.Intracomm,
    run_directory: Path,
    *,
    hard_stop_bytes: int,
    watchdog_hard_stop_bytes: int | None = None,
) -> dict[str, Any]:
    """Record actual V6-2 environment facts before any system construction."""

    from benchmarks.task034_wsl_resources import wsl_memory_snapshot
    from benchmarks.task040_level_a import _worker_current_resource

    worker_hard_stop_bytes = int(hard_stop_bytes)
    observed_watchdog_hard_stop = (
        None if watchdog_hard_stop_bytes is None else int(watchdog_hard_stop_bytes)
    )
    memory = wsl_memory_snapshot()
    disk = shutil.disk_usage(run_directory.parent)
    current = _worker_current_resource(comm, hard_limit_bytes=worker_hard_stop_bytes)
    scalar = np.dtype(PETSc.ScalarType)
    minimum_mem_available_bytes = (
        worker_hard_stop_bytes + V6_2_RESOURCE_HEADROOM_BYTES
    )
    thread_environment = {
        name: os.environ.get(name)
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "BLIS_NUM_THREADS",
        )
    }
    mem_available = memory.get("mem_available_bytes")
    local = {
        "comm_size": int(comm.size),
        "petsc_scalar_type": str(scalar),
        "petsc_int_type": str(PETSc.IntType),
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        )
        == "1",
        "python": sys.executable,
        "mem_available_bytes": mem_available,
        "minimum_mem_available_bytes": minimum_mem_available_bytes,
        "disk_free_bytes": int(disk.free),
        "swap_bytes": int(current.get("swap_bytes", -1)),
        "all_status_readable": bool(current.get("all_status_readable", False)),
        "hard_stop_bytes": worker_hard_stop_bytes,
        "watchdog_hard_stop_bytes": observed_watchdog_hard_stop,
        "thread_environment": thread_environment,
    }
    local["checks"] = {
        "mpi_size_8": local["comm_size"] == 8,
        "petsc_complex128": scalar == np.dtype(np.complex128),
        "qualified_activation": local["qualified_activation"],
        "mem_available_at_least_minimum": (
            isinstance(mem_available, (int, float))
            and not isinstance(mem_available, bool)
            and int(mem_available) >= minimum_mem_available_bytes
        ),
        "disk_at_least_20_gib": local["disk_free_bytes"] >= V6_2_MIN_DISK_FREE_BYTES,
        "swap_zero": local["swap_bytes"] == 0,
        "process_tree_readable": local["all_status_readable"],
        "below_watchdog_hard_stop": bool(current.get("pass", False)),
        "watchdog_hard_stop_matches_worker": (
            observed_watchdog_hard_stop is not None
            and worker_hard_stop_bytes == observed_watchdog_hard_stop
        ),
        "thread_environment_one": all(
            value == "1" for value in thread_environment.values()
        ),
    }
    local["pass"] = all(bool(value) for value in local["checks"].values())
    states = comm.allgather(local)
    checks = {
        name: all(bool(state.get("checks", {}).get(name)) for state in states)
        for name in local["checks"]
    }
    return {
        "schema": "task040.v6_2.resource_preflight.v1",
        "status": "pass" if all(checks.values()) else "not_run_by_resource_preflight",
        "pass": all(checks.values()),
        "checks": checks,
        "ranks": states,
        "hard_stop_bytes": worker_hard_stop_bytes,
        "watchdog_hard_stop_bytes": observed_watchdog_hard_stop,
        "minimum_mem_available_bytes": minimum_mem_available_bytes,
        "minimum_disk_free_bytes": V6_2_MIN_DISK_FREE_BYTES,
        "swap_limit_bytes": 0,
        "numeric_allgather": False,
        "thread_environment_required": {
            name: "1"
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        },
    }


def _stop_result(
    *,
    status: str,
    classification: str,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    identity_preflight: Mapping[str, Any],
    resource_preflight: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema": V6_2_INTERFACE_SCHUR_SCHEMA,
        "method": V6_2_INTERFACE_SCHUR_METHOD,
        "profile": V6_2_INTERFACE_SCHUR_PROFILE_ID,
        "status": status,
        "classification": classification,
        "source_sha": str(source_sha),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "identity_preflight": _json_safe(identity_preflight),
        "resource_preflight": (
            None if resource_preflight is None else _json_safe(resource_preflight)
        ),
        "system_created": False,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "numeric_allgather": False,
        "full_interface_numeric_replica": False,
        "downstream": {
            "full_spectrum": "not_run_by_v6_2_preflight",
            "moving_pml": "not_run_by_v6_2_preflight",
            "adaptive_schwarz": "not_run_by_v6_2_preflight",
            "factor_free_local_service": "not_run_by_v6_2_preflight",
        },
    }


def _fill_deterministic_interface_vector(vector: PETSc.Vec, vector_index: int) -> None:
    first, last = map(int, vector.getOwnershipRange())
    positions = np.arange(first, last, dtype=np.float64)
    scale = float(vector_index + 1)
    vector.array[:] = PETSc.ScalarType(
        scale * (0.125 + 0.00001 * positions)
        + 1j * (0.03125 * scale + 0.000003 * positions)
    )
    vector.assemble()


def _interior_residual_norm(
    comm: MPI.Intracomm,
    residual: PETSc.Vec,
    interior_rows: np.ndarray,
) -> float:
    first, last = map(int, residual.getOwnershipRange())
    rows = np.asarray(interior_rows, dtype=np.int64)
    if np.any(rows < first) or np.any(rows >= last):
        raise ValueError("V6-2 interior residual rows are not owner-local")
    values = np.asarray(residual.array[rows - first], dtype=np.complex128)
    local_squared = float(np.vdot(values, values).real)
    return float(np.sqrt(max(comm.allreduce(local_squared, op=MPI.SUM), 0.0)))


def _one_identity_probe(
    comm: MPI.Intracomm,
    bare: PETSc.Mat,
    matrix: PETSc.Mat,
    action: Any,
    vector_index: int,
) -> dict[str, Any]:
    source = action.create_interface_vector()
    target = matrix.createVecLeft()
    repeat_target = matrix.createVecLeft()
    residual = bare.createVecLeft()
    full_state: PETSc.Vec | None = None
    extracted: PETSc.Vec | None = None
    repeat_difference: PETSc.Vec | None = None
    roundtrip_difference: PETSc.Vec | None = None
    lower: PETSc.Vec | None = None
    upper: PETSc.Vec | None = None
    roundtrip: PETSc.Vec | None = None
    try:
        _fill_deterministic_interface_vector(source, vector_index)
        matrix.mult(source, target)
        matrix.mult(source, repeat_target)
        repeat_difference = target.duplicate()
        target.copy(repeat_difference)
        repeat_difference.axpy(PETSc.ScalarType(-1.0), repeat_target)

        full_state, state_audit = action.build_full_eliminated_state(source)
        bare.mult(full_state, residual)
        extracted = action.extract_interface_from_active_vector(residual)
        gamma_difference = target.duplicate()
        try:
            target.copy(gamma_difference)
            gamma_difference.axpy(PETSc.ScalarType(-1.0), extracted)
            gamma_error = float(gamma_difference.norm())
        finally:
            gamma_difference.destroy()

        lower, upper = action.restrict_interface(source)
        roundtrip = action.create_interface_vector()
        action.prolong_interface(lower, upper, roundtrip)
        roundtrip_difference = source.duplicate()
        source.copy(roundtrip_difference)
        roundtrip_difference.axpy(PETSc.ScalarType(-1.0), roundtrip)

        interior_error = _interior_residual_norm(
            comm,
            residual,
            np.asarray(state_audit["interior_rows_local"], dtype=np.int64),
        )
        return {
            "vector_index": int(vector_index),
            "gamma_action_error": _global_max(comm, gamma_error),
            "full_interior_residual_error": float(interior_error),
            "solve_count": int(state_audit["group_interior_solve_count"]),
            "roundtrip_error": _global_max(comm, float(roundtrip_difference.norm())),
            "repeat_error": _global_max(comm, float(repeat_difference.norm())),
        }
    finally:
        for vector in (
            roundtrip,
            upper,
            lower,
            roundtrip_difference,
            repeat_difference,
            extracted,
            full_state,
            residual,
            repeat_target,
            target,
            source,
        ):
            if vector is not None:
                vector.destroy()


def _linearity_probe(
    comm: MPI.Intracomm,
    matrix: PETSc.Mat,
    action: Any,
) -> float:
    left = action.create_interface_vector()
    right = action.create_interface_vector()
    combined = action.create_interface_vector()
    left_result = matrix.createVecLeft()
    right_result = matrix.createVecLeft()
    combined_result = matrix.createVecLeft()
    expected = matrix.createVecLeft()
    difference = matrix.createVecLeft()
    try:
        _fill_deterministic_interface_vector(left, 10)
        _fill_deterministic_interface_vector(right, 11)
        left.copy(combined)
        combined.axpy(PETSc.ScalarType(0.37 - 0.21j), right)
        matrix.mult(left, left_result)
        matrix.mult(right, right_result)
        matrix.mult(combined, combined_result)
        left_result.copy(expected)
        expected.scale(PETSc.ScalarType(1.0))
        expected.axpy(PETSc.ScalarType(0.37 - 0.21j), right_result)
        combined_result.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return _global_max(comm, float(difference.norm()))
    finally:
        for vector in (
            difference,
            expected,
            combined_result,
            right_result,
            left_result,
            combined,
            right,
            left,
        ):
            vector.destroy()


def run_v6_2_interface_schur(
    cfg: Any,
    profile: Any,
    *,
    comm: MPI.Intracomm,
    exact_spool_root: str | Path,
    run_directory: str | Path,
    source_sha: str,
    input_path: str | Path,
    input_sha256: str,
    physical_model_sha256: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    watchdog_enabled: bool = False,
    bottom_route_only: bool = False,
    hard_stop_bytes: int = 45 * 2**30,
    watchdog_hard_stop_bytes: int | None = None,
) -> dict[str, Any]:
    """Run the V6-2 identity route after metadata/resource preflight."""

    from benchmarks.task040_level_a import (
        _v5_authority_identity_preflight,
        _v5_write_operator_semantics_audit,
        audit_artificial_z_interface_support,
        build_current_gamma_layout,
        _petsc_matrix_hash,
        assemble_current_bare_f_authority_system,
    )

    output_root = Path(run_directory).resolve()
    frozen_root = Path(exact_spool_root).resolve()
    try:
        output_root.relative_to(frozen_root)
    except ValueError:
        pass
    else:
        raise ValueError("V6-2 output must not be below the frozen exact spool")
    if output_root == frozen_root:
        raise ValueError("V6-2 output must be disjoint from the frozen exact spool")
    if not output_root.is_absolute():
        raise ValueError("V6-2 output root must be absolute")

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
    identity_preflight = {**identity_preflight, "operator_semantics_audit_file": audit_file}
    _emit(
        marker_callback,
        "v6_2_identity_preflight",
        status=identity_preflight["status"],
        **{"pass": bool(identity_preflight["pass"])},
    )
    if not identity_preflight["pass"]:
        return _stop_result(
            status="not_run_by_identity_preflight",
            classification="V6_2_INTERFACE_IDENTITY_FAIL",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
            identity_preflight=identity_preflight,
            resource_preflight=None,
        )

    resource_preflight = _resource_preflight(
        comm,
        output_root,
        hard_stop_bytes=int(hard_stop_bytes),
        watchdog_hard_stop_bytes=watchdog_hard_stop_bytes,
    )
    _emit(
        marker_callback,
        "v6_2_resource_preflight",
        status=resource_preflight["status"],
        **{"pass": bool(resource_preflight["pass"])},
        checks=resource_preflight["checks"],
    )
    if not resource_preflight["pass"]:
        return _stop_result(
            status="not_run_by_resource_preflight",
            classification="V6_2_INTERFACE_RESOURCE_BLOCKED",
            source_sha=str(source_sha),
            input_sha256=str(input_sha256),
            physical_model_sha256=str(physical_model_sha256),
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
    matrix = None
    action = None
    try:
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=float(profile.bottom_interface_nm),
            top_interface_z_nm=float(profile.top_interface_nm),
            source_work_directory=output_root / "source",
            selected_mode_provider=None,
            external_mode_authority=identity_preflight["external_mode_authority"],
            external_mode_current_resolved_config_sha256=str(
                identity_preflight["observed"]["resolved_config_sha256"]
            ),
            comm=comm,
        )
        inventory = dict(system.construction_inventory)
        matrix_objects = dict(system.dtn_objects_constructed)
        if any(int(matrix_objects.get(name, -1)) != 0 for name in ("C", "D", "H")):
            raise RuntimeError("V6-2 bare-F assembly constructed C/D/H")
        if int(inventory.get("qep_calls", -1)) != 0:
            raise RuntimeError("V6-2 bare-F assembly observed qep_calls != 0")
        if any(
            bool(inventory.get(name))
            for name in (
                "physical_dtn_operator_constructed",
                "woodbury_inverse_constructed",
                "research_exact_side_lu_action_called",
            )
        ):
            raise RuntimeError("V6-2 assembly entered a forbidden side-operator path")
        _emit(
            marker_callback,
            "v6_2_system_ready",
            side="bottom",
            bare_f_rows=int(system.active_rows),
            factored_operator="none",
            matrix_objects=matrix_objects,
            qep_calls=0,
            full_side_exact_factor_count=0,
        )

        z_values = np.asarray(system.local_mesh.z_values, dtype=np.float64)
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
        canonical_layout = build_canonical_interface_layout(
            gamma_layouts["lower"],
            gamma_layouts["upper"],
            comm=comm,
            expected_lower_count=V6_2_INTERFACE_LOWER_COUNT,
            expected_upper_count=V6_2_INTERFACE_UPPER_COUNT,
        )
        group_rows, group_audit = build_v6_cell_recovery_owner_group_rows(
            system, system.F, comm=comm
        )
        first, last = map(int, system.F.getOwnershipRange())
        support_audits: dict[str, dict[str, Any]] = {}
        supports: list[np.ndarray] = []
        for name, z_value in (("lower", z_values[2]), ("upper", z_values[4])):
            support = audit_artificial_z_interface_support(
                system.V,
                system.static_condensation.condensed,
                float(z_value),
            )
            global_support = np.asarray(support["active_support"], dtype=np.int64)
            local_support = global_support[
                (global_support >= first) & (global_support < last)
            ].astype(PETSc.IntType, copy=False)
            supports.append(local_support)
            global_hash = hashlib.sha256(global_support.tobytes()).hexdigest()
            support_audits[name] = _support_summary(
                comm,
                local_support,
                global_count=int(global_support.size),
                global_hash=global_hash,
            )
        support_metadata_replicated = any(
            bool(audit.get("support_metadata_replicated"))
            for audit in support_audits.values()
        )
        oracle = build_petsc_interface_schur_oracle(system.F, group_rows, supports)
        matrix, action = build_petsc_full_interface_schur_action(
            oracle,
            canonical_layout=canonical_layout,
            own_oracle=True,
        )
        action_before = action.diagnostics
        bare_operator_hash = _petsc_matrix_hash(system.F)
        deterministic = [
            _one_identity_probe(comm, system.F, matrix, action, index)
            for index in range(3)
        ]
        zero_source = action.create_interface_vector()
        zero_target = matrix.createVecLeft()
        try:
            zero_source.set(0.0)
            zero_source.assemble()
            matrix.mult(zero_source, zero_target)
            zero_error = _global_max(comm, float(zero_target.norm()))
        finally:
            zero_target.destroy()
            zero_source.destroy()
        linearity_error = _linearity_probe(comm, matrix, action)
        factor_before = dict(action_before["factor_lifecycle"])
        layout_before = dict(action_before["interface_layout"])
        layout_gate = {
            "layout_coverage_exact": layout_before.get("coverage_exact") is True,
            "layout_counts_7560_plus_7560": (
                layout_before.get("lower_global_rows") == V6_2_INTERFACE_LOWER_COUNT
                and layout_before.get("upper_global_rows")
                == V6_2_INTERFACE_UPPER_COUNT
                and layout_before.get("global_size") == V6_2_INTERFACE_JOINT_COUNT
            ),
            "layout_canonical_l_then_u": (
                layout_before.get("canonical_order")
                == "Gamma_L_then_Gamma_U_by_physical_key"
            ),
            "layout_owner_distributed": layout_before.get("owner_distributed") is True,
            "layout_position_bijection": (
                layout_before.get("canonical_position_bijection") is True
            ),
        }
        lifecycle_gate = {
            "factor_ready_three_observed": factor_before.get("ready") == 3,
            "factor_simultaneous_max_three_observed": (
                factor_before.get("simultaneous_max") == 3
            ),
        }
        gate_before_cleanup = {
            "zero_map": zero_error <= V6_2_ZERO_TOLERANCE,
            "repeat": max(item["repeat_error"] for item in deterministic)
            <= V6_2_ROUNDTRIP_TOLERANCE,
            "linearity": linearity_error <= V6_2_ROUNDTRIP_TOLERANCE,
            "restriction_prolongation": max(
                item["roundtrip_error"] for item in deterministic
            )
            <= V6_2_ROUNDTRIP_TOLERANCE,
            "full_elimination_gamma": max(
                item["gamma_action_error"] for item in deterministic
            )
            <= V6_2_ACTION_TOLERANCE,
            "full_elimination_interior": max(
                item["full_interior_residual_error"] for item in deterministic
            )
            <= V6_2_ACTION_TOLERANCE,
            "three_deterministic_vectors": len(deterministic) == 3,
            "group_solve_count": all(item["solve_count"] == 3 for item in deterministic),
            "joint_size": int(action.global_size) == V6_2_INTERFACE_JOINT_COUNT,
            "numeric_allgather": not bool(action_before["numeric_allgather"]),
            "full_interface_replica": not bool(
                action_before["full_interface_numeric_replica"]
            ),
            **layout_gate,
            **lifecycle_gate,
        }
        _emit(
            marker_callback,
            "v6_2_identity_gate",
            checks=gate_before_cleanup,
            gate_pass=all(gate_before_cleanup.values()),
            vector_count=len(deterministic),
        )
        matrix.destroy()
        matrix = None
        action.destroy()
        action_after = action.diagnostics
        factor_after = dict(action_after["factor_lifecycle"])
        cleanup_gate = {
            "factor_after_cleanup_zero_observed": (
                factor_after.get("after_cleanup") == 0
            ),
            "factor_action_destroyed": action_after.get("destroyed") is True,
        }
        identity_gate = {**gate_before_cleanup, **cleanup_gate}
        identity_gate_pass = all(identity_gate.values())
        action = None
        system.destroy()
        system = None
        rank_artifact = {
            "schema": "task040.v6_2.rank_artifact.v1",
            "rank": int(comm.rank),
            "mpi_size": int(comm.size),
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "bare_f_operator_hash": str(bare_operator_hash),
            "identity_preflight": {
                "pass": bool(identity_preflight["pass"]),
                "observed": _json_safe(identity_preflight.get("observed", {})),
                "checks": _json_safe(identity_preflight.get("checks", {})),
            },
            "operator_semantics_audit": _json_safe(audit_file),
            "resource_preflight_pass": bool(resource_preflight["pass"]),
            "system_inventory": _json_safe(inventory),
            "matrix_objects": _json_safe(matrix_objects),
            "qep_calls": int(inventory["qep_calls"]),
            "canonical_interface_layout": _json_safe(action_before["interface_layout"]),
            "canonical_mapping_sha256": _local_mapping_sha256(
                canonical_layout.local_row_to_position
            ),
            "canonical_mapping_count": len(canonical_layout.local_row_to_position),
            "group_rows": _json_safe(group_audit),
            "support_audits": support_audits,
            "support_metadata_replicated": support_metadata_replicated,
            "deterministic_vectors": deterministic,
            "zero_error": float(zero_error),
            "linearity_error": float(linearity_error),
            "identity_gate": identity_gate,
            "gate_pass": identity_gate_pass,
            "classification": (
                "V6_2_FULL_INTERFACE_SCHUR_PASS"
                if identity_gate_pass
                else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
            ),
            "factor_lifecycle_observed": {
                "construction_count": int(factor_before["ready"]),
                "destruction_count": int(
                    factor_before["ready"] - factor_after["after_cleanup"]
                ),
                "simultaneous_max": int(factor_before["simultaneous_max"]),
                "after_cleanup": int(factor_after["after_cleanup"]),
            },
            "factor_lifecycle_before": _json_safe(
                action_before["factor_lifecycle"]
            ),
            "factor_lifecycle_after": _json_safe(
                action_after["factor_lifecycle"]
            ),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "numeric_allgather": False,
            "fe_numeric_allgather": False,
            "full_interface_numeric_replica": False,
            "raw_global_row_remap": False,
            "exact_output_vectors_loaded": 0,
            "pde_solve": "not_run",
            "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
        }
        rank_path = rank_root / "v6_2_rank_artifact.json"
        rank_sha = _write_json(rank_path, rank_artifact)
        rank_descriptor = {
            "rank": int(comm.rank),
            "path": str(rank_path.relative_to(output_root)),
            "sha256": rank_sha,
            "canonical_mapping_count": len(canonical_layout.local_row_to_position),
            "canonical_mapping_sha256": rank_artifact["canonical_mapping_sha256"],
            "factor_lifecycle_after": rank_artifact["factor_lifecycle_after"],
        }
        rank_descriptors = comm.gather(rank_descriptor, root=0)
        result = None
        if comm.rank == 0:
            rank_descriptors = sorted(rank_descriptors, key=lambda item: item["rank"])
            factor_after_by_rank = [
                item["factor_lifecycle_after"] for item in rank_descriptors
            ]
            construction_counts = [
                int(item["factor_lifecycle_after"]["ready"])
                for item in rank_descriptors
            ]
            destruction_counts = [
                int(item["factor_lifecycle_after"]["ready"])
                - int(item["factor_lifecycle_after"]["after_cleanup"])
                for item in rank_descriptors
            ]
            simultaneous_counts = [
                int(item["factor_lifecycle_after"]["simultaneous_max"])
                for item in rank_descriptors
            ]
            factor_lifecycle = {
                "before": _json_safe(action_before["factor_lifecycle"]),
                "after_by_rank": factor_after_by_rank,
                "construction_count": construction_counts[0]
                if len(set(construction_counts)) == 1
                else None,
                "destruction_count": destruction_counts[0]
                if len(set(destruction_counts)) == 1
                else None,
                "simultaneous_max": max(simultaneous_counts)
                if simultaneous_counts
                else None,
                "rank_consensus": (
                    len(set(construction_counts)) == 1
                    and len(set(destruction_counts)) == 1
                    and len(set(simultaneous_counts)) == 1
                ),
            }
            result = {
                "schema": V6_2_INTERFACE_SCHUR_SCHEMA,
                "method": V6_2_INTERFACE_SCHUR_METHOD,
                "profile": V6_2_INTERFACE_SCHUR_PROFILE_ID,
                "mpi_size": int(comm.size),
                "status": (
                    "completed_v6_2_identity"
                    if identity_gate_pass
                    else "completed_v6_2_identity_gate_negative"
                ),
                "classification": (
                    "V6_2_FULL_INTERFACE_SCHUR_PASS"
                    if identity_gate_pass
                    else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
                ),
                "source_sha": str(source_sha),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "identity_preflight": _json_safe(identity_preflight),
                "resource_preflight": _json_safe(resource_preflight),
                "operator_semantics_audit": _json_safe(audit_file),
                "system_created": True,
                "system_inventory": _json_safe(inventory),
                "matrix_objects": _json_safe(matrix_objects),
                "qep_calls": int(inventory["qep_calls"]),
                "bare_f_operator_hash": str(bare_operator_hash),
                "factored_operator": "none",
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "exact_output_vectors_loaded": 0,
                "pde_solve": "not_run",
                "canonical_interface_layout": _json_safe(
                    action_before["interface_layout"]
                ),
                "gamma_counts": {
                    "Gamma_L": V6_2_INTERFACE_LOWER_COUNT,
                    "Gamma_U": V6_2_INTERFACE_UPPER_COUNT,
                    "joint": V6_2_INTERFACE_JOINT_COUNT,
                },
                "group_rows": _json_safe(group_audit),
                "support_audits": support_audits,
                "support_metadata_replicated": support_metadata_replicated,
                "deterministic_vectors": deterministic,
                "zero_error": float(zero_error),
                "linearity_error": float(linearity_error),
                "identity_gate": identity_gate,
                "gate_pass": identity_gate_pass,
                "factor_lifecycle": factor_lifecycle,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "full_interface_numeric_replica": False,
                "root_metadata_gather": True,
                "per_rank_full_interface_replica": False,
                "raw_global_row_remap": False,
                "rank_artifacts": rank_descriptors,
                "downstream": {
                    "v6_3_full_spectrum": "not_run_by_v6_2_identity_only",
                    "v6_4_route_a_b": "not_run_by_v6_2_identity_only",
                    "v6_5_moving_pml": "not_run_by_v6_2_identity_only",
                    "v6_6_adaptive_schwarz": "not_run_by_v6_2_identity_only",
                    "v6_7_factor_free_local_service": "not_run_by_v6_2_identity_only",
                    "v6_8_full_hybrid": "not_run_by_v6_2_identity_only",
                    "v6_9_capacity": "not_run_by_v6_2_identity_only",
                },
                "exact_qualification_plan": build_v6_2_exact_qualification_plan(),
                "research_only": True,
            }
            _write_json(output_root / "v6_2_manifest.json", result)
        result = comm.bcast(result, root=0)
        comm.barrier()
        return _json_safe(result)
    finally:
        if action is not None:
            action.destroy()
        if matrix is not None:
            matrix.destroy()
        if system is not None:
            system.destroy()
