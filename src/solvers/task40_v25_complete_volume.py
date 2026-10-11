"""Complete target-volume Schur action witness for the Task40 V25 window.

This module builds only local volume condensation, its matrix-free trace
action, and an independent full-space curl-plus-mass action. It does not build
DtN carrier data, q matrices, a global matrix, a factor, or a KSP.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from petsc4py import PETSc

from .hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from .p6_cell_condensed_action import P6CellCondensedAction


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(repr((array.shape, str(array.dtype))).encode("ascii"))
    digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _relative_error(error: np.ndarray, reference: np.ndarray) -> tuple[float, float, float]:
    error_norm = float(np.linalg.norm(error))
    reference_norm = float(np.linalg.norm(reference))
    if reference_norm == 0.0:
        return (0.0 if error_norm == 0.0 else float("inf"), error_norm, reference_norm)
    return error_norm / reference_norm, error_norm, reference_norm


def _relative_error_between(
    left: np.ndarray, right: np.ndarray, *, chunk_entries: int = 1_000_000
) -> tuple[float, float, float]:
    """Compute a complex relative norm without allocating a full-size delta."""
    lhs = np.asarray(left).reshape(-1)
    rhs = np.asarray(right).reshape(-1)
    if lhs.shape != rhs.shape:
        raise ValueError("V25 error operands have different shapes")
    error_square = 0.0
    reference_square = 0.0
    for start in range(0, lhs.size, int(chunk_entries)):
        stop = min(start + int(chunk_entries), lhs.size)
        delta = np.subtract(lhs[start:stop], rhs[start:stop])
        error_square += float(np.vdot(delta, delta).real)
        reference_square += float(np.vdot(rhs[start:stop], rhs[start:stop]).real)
    error_norm = float(np.sqrt(error_square))
    reference_norm = float(np.sqrt(reference_square))
    if reference_norm == 0.0:
        return (0.0 if error_norm == 0.0 else float("inf"), error_norm, reference_norm)
    return error_norm / reference_norm, error_norm, reference_norm


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_save_array(output_directory: Path, name: str, value: np.ndarray) -> dict[str, Any]:
    """Atomically persist one raw array and verify it from a read-only mmap."""
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise TypeError("V25 witness arrays cannot contain Python objects")
    destination = output_directory / name
    if destination.exists():
        raise FileExistsError(f"V25 raw witness already exists: {destination.name}")
    temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        np.save(stream, array, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    directory_fd = os.open(output_directory, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    array_digest = _array_sha256(array)
    readback = np.load(destination, mmap_mode="r", allow_pickle=False)
    try:
        if readback.shape != array.shape or readback.dtype != array.dtype:
            raise IOError(f"V25 raw witness readback shape/dtype differs: {destination.name}")
        if _array_sha256(readback) != array_digest:
            raise IOError(f"V25 raw witness readback array hash differs: {destination.name}")
    finally:
        del readback
    return {
        "path": destination.name,
        "file_sha256": _file_sha256(destination),
        "array_sha256": array_digest,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "bytes": int(destination.stat().st_size),
        "readback_verified": True,
    }


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _native_action_owner_bound(
    *,
    function_space: Any,
    mpc: Any,
    cell_count: int,
    local_dofs_per_cell: int,
) -> dict[str, int | str]:
    """Estimate retained Functions, PETSc outputs, MPC maps and packed fields."""
    index_map = function_space.dofmap.index_map
    owned = int(index_map.size_local)
    ghost = int(index_map.num_ghosts)
    local_storage = owned + ghost
    slaves = np.asarray(mpc.slaves, dtype=np.int32).reshape(-1)
    owned_slave_count = int(np.count_nonzero((slaves >= 0) & (slaves < owned)))
    coefficients, offsets = mpc.coefficients()
    offsets = np.asarray(offsets, dtype=np.int64)
    flat_count = 0
    for row in slaves:
        row_i = int(row)
        flat_count += int(offsets[row_i + 1] - offsets[row_i])
    scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    index_bytes = int(np.dtype(np.int32).itemsize)
    per_component = {
        "function_coefficient_bytes": local_storage * scalar_bytes,
        "output_vector_bytes": local_storage * scalar_bytes,
        "constraint_gather_work_bytes": flat_count * scalar_bytes,
        "owned_slave_work_bytes": owned_slave_count * scalar_bytes,
        "slave_indices_bytes": len(slaves) * index_bytes,
        "owned_slave_indices_bytes": owned_slave_count * index_bytes,
        "flat_slave_indices_bytes": flat_count * index_bytes,
        "master_indices_bytes": flat_count * index_bytes,
        "conjugated_master_coefficients_bytes": flat_count * scalar_bytes,
        "packed_constants_upper_bytes": 64 * 2**20,
    }
    retained_two_components = 2 * sum(per_component.values())
    packed_coefficients_peak = 2 * cell_count * local_dofs_per_cell * scalar_bytes
    assembler_workspace_upper = 512 * 2**20
    return {
        "schema": "task40extra.review_v25_fullspace_action_owner_preflight.v1",
        "local_owned_rows": owned,
        "local_ghost_rows": ghost,
        "local_storage_entries": local_storage,
        "local_slave_rows": int(len(slaves)),
        "owned_slave_rows": owned_slave_count,
        "MPC_master_coefficients_copied_per_component": flat_count,
        "per_component_retained_bytes_upper": int(sum(per_component.values())),
        "per_component_components": per_component,
        "two_component_retained_bytes_upper": int(retained_two_components),
        "packed_coefficients_peak_bytes_upper": int(packed_coefficients_peak),
        "assembler_and_native_workspace_bytes_upper": int(assembler_workspace_upper),
        "additional_bytes_upper": int(
            retained_two_components + packed_coefficients_peak + assembler_workspace_upper
        ),
        "packed_coefficients_bound_scope": (
            "two full cell-wise complex p6 coefficient tables; the split action packs one component at a time"
        ),
    }


def _deterministic_trace_input(size: int, *, case: int) -> np.ndarray:
    index = np.arange(size, dtype=np.float64)
    shift = float(case + 1)
    result = np.ascontiguousarray(
        (0.7 + 0.2 * np.sin((index + shift) * 0.017))
        * np.exp(1j * (0.0031 * (index + 1.0) * shift + 0.13 * shift)),
        dtype=np.complex128,
    )
    if result.size and np.any(result == 0.0):
        raise RuntimeError("deterministic V25 witness unexpectedly contains zero trace values")
    return result


def _p6_action_owner_bound(
    *,
    cell_count: int,
    local_dofs_per_cell: int,
    trace_rows_per_cell: int,
    maximum_masters_per_slave: int,
    index_bytes: int,
) -> dict[str, int | str]:
    """Bound retained per-cell CSR and Python owners built by P6 action."""
    max_entries = trace_rows_per_cell * max(1, maximum_masters_per_slave)
    csr_bytes = cell_count * (
        max_entries * (index_bytes + np.dtype(np.complex128).itemsize)
        + (trace_rows_per_cell + 1) * index_bytes
    )
    active_ids_bytes = cell_count * trace_rows_per_cell * index_bytes
    original_cell_row_copies_bytes = cell_count * local_dofs_per_cell * index_bytes
    python_bytes = cell_count * 768
    return {
        "schema": "task40extra.review_v25_p6_action_owner_preflight.v1",
        "status": "DERIVED_UPPER_BOUND",
        "cell_count": int(cell_count),
        "trace_rows_per_cell": int(trace_rows_per_cell),
        "maximum_masters_per_slave": int(maximum_masters_per_slave),
        "max_expansion_entries_per_cell": int(max_entries),
        "per_cell_expansion_csr_bytes_upper": int(csr_bytes),
        "per_cell_active_id_bytes_upper": int(active_ids_bytes),
        "per_cell_original_interior_and_trace_row_copies_bytes_upper": int(
            original_cell_row_copies_bytes
        ),
        "python_cell_metadata_bytes_upper": int(python_bytes),
        "additional_bytes_upper": int(
            csr_bytes + active_ids_bytes + original_cell_row_copies_bytes + python_bytes
        ),
        "scope": (
            "P6CellCondensedAction._build_cells sparse expansions, active ids, and cell records; "
            "local Schur/LU/recovery arrays are borrowed"
        ),
    }


def _frozen_cell_class_coverage(build_audit: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the condensed builder's actual audit fields with the frozen inventory."""
    expected = {
        "owned_cell_count_global": 30_464,
        "raw_tensor_class_count_global_unique": 29,
        "oriented_schur_class_count_sum": 60,
    }
    actual = {name: build_audit.get(name) for name in expected}
    missing_fields = [name for name in expected if name not in build_audit]
    mismatched_fields = {
        name: {"expected": value, "actual": actual[name]}
        for name, value in expected.items()
        if name in build_audit and actual[name] != value
    }
    return {
        "schema": "task40extra.review_v25_cell_class_coverage.v1",
        "source": "condensed.build_audit",
        "status": "PASS" if not missing_fields and not mismatched_fields else "FAILED",
        "expected_counts": expected,
        "actual_counts": actual,
        "missing_fields": missing_fields,
        "mismatched_fields": mismatched_fields,
        "builder_audit_excerpt": {
            name: build_audit.get(name)
            for name in (
                "raw_tensor_class_count_sum",
                "raw_tensor_class_use_count_sum",
                "retained_local_schur_class_count_sum",
            )
            if name in build_audit
        },
    }


def run_complete_target_volume_action(
    *,
    cfg: Any,
    mesh_object: Any,
    cell_tags: Any,
    function_space: Any,
    mpc: Any,
    output_directory: Path,
    resource_admission: Callable[[str, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """Run two full-grid manufactured volume witnesses with independent RHS."""
    from dolfinx import fem
    import ufl

    from .common_3d_forms import _build_physical_volume_terms
    from .fullspace_physical_action import FullspaceSplitVolumeAction

    started = time.perf_counter()
    if mesh_object.comm.size != 1:
        raise NotImplementedError("V25 compact target-volume action is qualified for MPI1")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise TypeError("V25 complete target-volume action requires complex128 PETSc")
    if int(function_space.element.space_dimension) != 882:
        raise ValueError("V25 target-volume action requires the actual p6 882-row element")
    if int(function_space.dofmap.index_map_bs) != 1:
        raise ValueError("V25 target-volume action requires scalar-blocked H(curl)")
    cell_count = int(mesh_object.topology.index_map(mesh_object.topology.dim).size_local)
    full_rows = int(function_space.dofmap.index_map.size_global)
    if cell_count != 30_464 or full_rows != 20_181_348:
        raise ValueError(
            f"V25 target inventory changed: cells={cell_count}, storage_rows={full_rows}"
        )

    index_map = function_space.dofmap.index_map
    local_slaves = np.asarray(mpc.slaves, dtype=np.int32).reshape(-1)
    owned_slaves = local_slaves[
        (local_slaves >= 0) & (local_slaves < int(index_map.size_local))
    ]
    slave_rows = np.asarray(index_map.local_to_global(owned_slaves), dtype=np.int64).reshape(-1)
    slave_rows.sort()
    if len(np.unique(slave_rows)) != len(slave_rows):
        raise ValueError("V25 finalized MPC contains duplicate owned slave rows")
    if full_rows - len(slave_rows) != 19_897_344:
        raise ValueError("V25 finalized MPC independent-row inventory changed")
    output_directory = Path(output_directory).resolve()
    if not output_directory.is_dir():
        raise FileNotFoundError("V25 run output directory must already exist")

    gates: list[dict[str, Any]] = []

    def admit(stage: str, additional_bytes: int) -> dict[str, Any]:
        record = dict(resource_admission(stage, int(additional_bytes)))
        gates.append(record)
        return record

    trial = ufl.TrialFunction(function_space)
    test = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_object, subdomain_data=cell_tags)
    curl_form, mass_form = _build_physical_volume_terms(cfg, trial, test, dx)
    compiled_form = fem.form(curl_form + mass_form)
    native_owner_bound = _native_action_owner_bound(
        function_space=function_space,
        mpc=mpc,
        cell_count=cell_count,
        local_dofs_per_cell=int(function_space.element.space_dimension),
    )
    native_owner_preflight = admit(
        "v25_fullspace_split_native_owner_capacity_preflight_before_condensation",
        int(native_owner_bound["additional_bytes_upper"]),
    )
    native_action = None
    condensed = None
    p6_action = None
    witnesses: list[dict[str, Any]] = []
    try:
        def builder_gate(stage: str, facts: Mapping[str, Any]) -> None:
            facts = dict(facts)
            if stage == "compact_action_only_maps_preflight":
                additional = int(facts.get("retained_numeric_bytes_upper", 0)) + int(
                    facts.get("workspace_bytes", 0)
                )
            else:
                additional = int(
                    facts.get("retained_numeric_bytes_upper", 0)
                ) + int(
                    facts.get("additional_payload_bytes", facts.get("matrix_payload_bytes", 0))
                ) + int(facts.get("workspace_bytes", facts.get("workspace_bytes_upper", 0)))
            admit(f"v25_condensation/{stage}", additional)

        condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            function_space,
            cell_tags,
            mpc=mpc,
            appended_global_rows=0,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            share_identity_cache=True,
            preserve_exact_geometry=True,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            compact_action_only_maps=True,
            allocation_gate=builder_gate,
        )
        if condensed.matrix is not None or condensed.retained_local_schur_by_class is None:
            raise RuntimeError("V25 volume condensation unexpectedly materialized a global matrix")
        class_coverage = _frozen_cell_class_coverage(condensed.build_audit)
        _atomic_write_json(
            output_directory / "v25_cell_class_coverage.json",
            class_coverage,
        )
        if class_coverage["status"] != "PASS":
            detail = json.dumps(
                {
                    "actual_counts": class_coverage["actual_counts"],
                    "missing_fields": class_coverage["missing_fields"],
                    "mismatched_fields": class_coverage["mismatched_fields"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            raise ValueError(f"V25 complete target volume cell-class coverage mismatch: {detail}")
        map_audit = condensed.build_audit.get("compact_action_only_maps")
        if not isinstance(map_audit, Mapping) or map_audit.get("status") != "DERIVED_UPPER_BOUND":
            raise ValueError("V25 compact-map allocation gate did not produce a preflight receipt")

        constraint_audit = condensed.trace_constraints.build_audit
        owner_bound = _p6_action_owner_bound(
            cell_count=cell_count,
            local_dofs_per_cell=int(function_space.element.space_dimension),
            trace_rows_per_cell=int(condensed.build_audit["local_trace_dimension"]),
            maximum_masters_per_slave=int(
                constraint_audit.get("maximum_masters_per_slave", 1)
            ),
            index_bytes=int(np.dtype(PETSc.IntType).itemsize),
        )
        p6_constructor_workspace = (
            3 * full_rows * np.dtype(np.complex128).itemsize
            + 2 * condensed.active_rows * np.dtype(np.complex128).itemsize
            + 256 * 2**20
        )
        owner_bound["constructor_workspace_bytes_upper"] = int(p6_constructor_workspace)
        owner_bound["combined_owner_and_workspace_bytes_upper"] = int(
            int(owner_bound["additional_bytes_upper"]) + p6_constructor_workspace
        )
        combined_owner_and_workspace_bytes = (
            int(native_owner_bound["additional_bytes_upper"])
            + int(owner_bound["additional_bytes_upper"])
            + p6_constructor_workspace
        )
        native_owner_admission = admit(
            "v25_native_and_p6_owners_plus_constructor_workspace_before_construction",
            combined_owner_and_workspace_bytes,
        )
        native_action = FullspaceSplitVolumeAction(
            curl_form, mass_form, function_space, mpc=mpc
        )
        full_vector_bytes = full_rows * np.dtype(np.complex128).itemsize
        p6_action = P6CellCondensedAction(
            condensed,
            H_p=np.zeros((0, 0), dtype=np.complex128),
        )
        owner_admission = native_owner_admission
        if (
            p6_action.reduced_size != condensed.active_rows
            or condensed.appended_rows != 0
            or len(condensed.cell_recovery_maps) != cell_count
        ):
            raise ValueError("V25 S-only action has an incomplete trace or cell owner")
        active_bytes = condensed.active_rows * np.dtype(np.complex128).itemsize
        per_case_disk_upper = (
            5 * full_vector_bytes + 3 * active_bytes + len(slave_rows) * 8
            + 2 * cell_count * np.dtype(np.int64).itemsize + 4096
        )
        disk_required = 2 * per_case_disk_upper + full_vector_bytes
        free_disk = int(shutil.disk_usage(output_directory).free)
        disk_gate = {
            "stage": "v25_two_case_atomic_raw_witness_persistence",
            "required_bytes_upper": int(disk_required),
            "available_bytes": free_disk,
            "passed": bool(free_disk >= disk_required),
            "scope": "five full and three active complex128 arrays per case, slave/cell diagnostics, and one largest atomic temporary",
        }
        gates.append(disk_gate)
        if not disk_gate["passed"]:
            raise VolumeResourceBlocked(disk_gate)

        for case in (0, 1):
            case_path = output_directory / f"v25_volume_witness_case_{case}.json"
            saved_arrays: list[dict[str, Any]] = []
            source_vec = recovered_vec = None
            try:
                admit(
                    f"v25_witness_{case}_native_forms_arrays_and_packed_coefficient_peak",
                    5 * full_vector_bytes
                    + 3 * active_bytes
                    + int(native_owner_bound["packed_coefficients_peak_bytes_upper"])
                    + 256 * 2**20,
                )
                active_input = _deterministic_trace_input(condensed.active_rows, case=case)
                storage = np.zeros(full_rows, dtype=np.complex128)
                active_original = np.asarray(
                    condensed.trace_constraints.owned_active_original_dofs, dtype=np.int64
                )
                storage[active_original] = active_input
                internal_nonzero_counts = np.zeros(cell_count, dtype=np.int64)
                for cell_index, cell in enumerate(condensed.cell_recovery_maps):
                    rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                    if case == 1:
                        local = np.arange(len(rows), dtype=np.float64)
                        storage[rows] = (
                            0.25 + 1.0e-5 * (cell_index + local + 1.0)
                            + 1j * (0.125 + 2.0e-5 * (2 * cell_index + local + 1.0))
                        )
                    internal_nonzero_counts[cell_index] = int(np.count_nonzero(storage[rows]))
                nonzero_internal_cells = int(np.count_nonzero(internal_nonzero_counts))
                if storage.shape != (full_rows,) or not np.isfinite(storage).all():
                    raise FloatingPointError("V25 manufactured full-storage state is invalid")
                if len(slave_rows) and np.any(storage[slave_rows] != 0.0):
                    raise ValueError("V25 manufactured storage must keep MPC slave rows exactly zero")
                if not np.array_equal(storage[active_original], active_input):
                    raise ValueError("V25 manufactured storage lost an active trace input value")
                if case == 1 and nonzero_internal_cells != cell_count:
                    raise FloatingPointError(
                        "V25 second input lacks a nonzero internal state in every target cell"
                    )

                source_vec = PETSc.Vec().createWithArray(storage, comm=PETSc.COMM_SELF)
                source_vec.assemble()
                native_rhs_owner = native_action.apply(source_vec)
                frozen_rhs = np.array(
                    native_rhs_owner.getArray(readonly=True), dtype=np.complex128, copy=True
                )
                frozen_rhs.setflags(write=False)
                if frozen_rhs.shape != (full_rows,) or not np.isfinite(frozen_rhs).all():
                    raise FloatingPointError("V25 independent native volume RHS is invalid")
                if len(slave_rows) and np.any(frozen_rhs[slave_rows] != 0.0):
                    raise ValueError("V25 native MPC-dual RHS must keep slave rows exactly zero")

                reduced_rhs = p6_action.reduce_rhs(frozen_rhs, rhs_is_mpc_dual=True)
                reduced_action = p6_action.apply(active_input)
                action_relative, action_error_norm, reduced_rhs_norm = _relative_error_between(
                    reduced_action, reduced_rhs
                )
                admit(
                    f"v25_witness_{case}_recovery_and_independent_native_callback",
                    3 * full_vector_bytes + int(native_owner_bound[
                        "packed_coefficients_peak_bytes_upper"
                    ]),
                )
                recovered = p6_action.recover_storage(
                    active_input, full_rhs=frozen_rhs, expand_trace=False
                )
                if len(slave_rows) and np.any(recovered[slave_rows] != 0.0):
                    raise ValueError("V25 recovered storage must keep MPC slave rows exactly zero")
                forward_relative, forward_error_norm, storage_norm = _relative_error_between(
                    recovered, storage
                )
                native_rhs_norm = float(np.linalg.norm(frozen_rhs))
                correction_history: list[dict[str, Any]] = []
                residual = None
                native_recovered_action = None

                for correction_index in range(4):
                    recovered_vec = PETSc.Vec().createWithArray(
                        recovered, comm=PETSc.COMM_SELF
                    )
                    recovered_vec.assemble()
                    native_recovered_owner = native_action.apply(recovered_vec)
                    native_recovered_action = np.array(
                        native_recovered_owner.getArray(readonly=True),
                        dtype=np.complex128,
                        copy=True,
                    )
                    residual = np.subtract(frozen_rhs, native_recovered_action)
                    native_relative, native_error_norm, current_native_rhs_norm = _relative_error(
                        residual, frozen_rhs
                    )
                    correction_history.append(
                        {
                            "same_lu_correction_index": correction_index,
                            "condensed_action_rhs_relative_error": float(action_relative),
                            "native_volume_residual_relative": float(native_relative),
                            "native_volume_residual_norm": float(native_error_norm),
                            "native_rhs_norm": float(current_native_rhs_norm),
                            "recovery_forward_relative_error": float(forward_relative),
                            "recovery_forward_error_norm": float(forward_error_norm),
                            "action_gate_status": (
                                "PASS" if action_relative <= 1.0e-10 else "FAILED"
                            ),
                            "native_residual_gate_status": (
                                "PASS" if native_relative <= 1.0e-10 else "FAILED"
                            ),
                            "forward_gate_status": (
                                "PASS" if forward_relative <= 1.0e-11 else "FAILED"
                            ),
                            "status": (
                                "PASS"
                                if action_relative <= 1.0e-10
                                and native_relative <= 1.0e-10
                                and forward_relative <= 1.0e-11
                                else "GATE_PENDING_OR_FAILED"
                            ),
                        }
                    )
                    if forward_relative <= 1.0e-11 or correction_index == 3:
                        recovered_vec.destroy()
                        recovered_vec = None
                        break
                    admit(
                        f"v25_witness_{case}_same_lu_correction_{correction_index + 1}",
                        full_vector_bytes + int(native_owner_bound[
                            "packed_coefficients_peak_bytes_upper"
                        ]),
                    )
                    next_recovered = p6_action.correct_internal_storage(recovered, residual)
                    recovered_vec.destroy()
                    recovered_vec = None
                    del native_recovered_action, residual
                    native_recovered_action = residual = None
                    del recovered
                    recovered = next_recovered
                    forward_relative, forward_error_norm, storage_norm = _relative_error_between(
                        recovered, storage
                    )

                if residual is None or native_recovered_action is None:
                    raise RuntimeError("V25 native residual callback did not produce its output")
                packed_bytes_by_component = {
                    name: int(action.audit.get("last_packed_coefficient_bytes", 0))
                    for name, action in native_action.component_actions.items()
                }
                packed_coefficients_within_bound = max(
                    packed_bytes_by_component.values(), default=0
                ) <= int(native_owner_bound["packed_coefficients_peak_bytes_upper"])

                b_nonzero_counts = np.zeros(cell_count, dtype=np.int64)
                b_norms = np.zeros(cell_count, dtype=np.float64)
                for cell_index, cell in enumerate(condensed.cell_recovery_maps):
                    rows = np.asarray(cell.interior_original_dofs, dtype=np.int64)
                    local_b = frozen_rhs[rows]
                    b_nonzero_counts[cell_index] = int(np.count_nonzero(local_b))
                    b_norms[cell_index] = float(np.linalg.norm(local_b))
                nonzero_b_cells = int(np.count_nonzero(b_nonzero_counts))
                if case == 1 and nonzero_b_cells != cell_count:
                    correction_history.append(
                        {"status": "FAILED_INTERNAL_RHS_CELL_COVERAGE", "nonzero_b_cells": nonzero_b_cells}
                    )

                raw_values = (
                    ("trace_input", active_input),
                    ("storage_state", storage),
                    ("native_rhs", frozen_rhs),
                    ("reduced_rhs", reduced_rhs),
                    ("reduced_action", reduced_action),
                    ("recovered_storage", recovered),
                    ("native_recovered_action", native_recovered_action),
                    ("native_residual", residual),
                    ("slave_global_rows", np.asarray(slave_rows, dtype=np.int64)),
                    ("internal_state_nonzero_counts_by_cell", internal_nonzero_counts),
                    ("internal_rhs_nonzero_counts_by_cell", b_nonzero_counts),
                    ("internal_rhs_norms_by_cell", b_norms),
                )
                for label, array in raw_values:
                    saved_arrays.append(
                        _atomic_save_array(
                            output_directory,
                            f"v25_volume_case_{case}_{label}.npy",
                            array,
                        )
                    )
                del raw_values, array, label
                native_relative, native_error_norm, native_rhs_norm = _relative_error(
                    residual, frozen_rhs
                )
                passed = bool(
                    np.isfinite(action_relative)
                    and np.isfinite(native_relative)
                    and np.isfinite(forward_relative)
                    and packed_coefficients_within_bound
                    and action_relative <= 1.0e-10
                    and native_relative <= 1.0e-10
                    and forward_relative <= 1.0e-11
                    and (case != 1 or nonzero_b_cells == cell_count)
                )
                witness = {
                    "case": int(case),
                    "active_trace_input_sha256": _array_sha256(active_input),
                    "full_storage_input_sha256": _array_sha256(storage),
                    "native_rhs_sha256": _array_sha256(frozen_rhs),
                    "active_trace_rows": int(condensed.active_rows),
                    "active_trace_nonzero_count": int(np.count_nonzero(active_input)),
                    "target_cell_count": cell_count,
                    "nonzero_internal_cell_count": nonzero_internal_cells,
                    "internal_state_nonzero_counts_by_cell_sha256": _array_sha256(internal_nonzero_counts),
                    "all_cell_internal_nonzero_witness": case == 1 and nonzero_internal_cells == cell_count,
                    "native_rhs_nonzero_internal_cell_count": nonzero_b_cells,
                    "native_rhs_nonzero_counts_by_cell_sha256": _array_sha256(b_nonzero_counts),
                    "native_rhs_norms_by_cell_sha256": _array_sha256(b_norms),
                    "all_cell_internal_native_rhs_witness": case == 1 and nonzero_b_cells == cell_count,
                    "slave_storage_exact_zero": bool(
                        not len(slave_rows) or np.all(storage[slave_rows] == 0.0)
                    ),
                    "native_rhs_is_mpc_dual": True,
                    "native_rhs_slave_storage_exact_zero": bool(
                        not len(slave_rows) or np.all(frozen_rhs[slave_rows] == 0.0)
                    ),
                    "rhs_copy_frozen_before_output_reuse": True,
                    "rhs_reduction_uses_mpc_dual": True,
                    "recovery_expand_trace": False,
                    "condensed_action_rhs_relative_error": float(action_relative),
                    "condensed_action_rhs_error_norm": float(action_error_norm),
                    "condensed_rhs_norm": float(reduced_rhs_norm),
                    "native_volume_residual_relative": float(native_relative),
                    "native_volume_residual_norm": float(native_error_norm),
                    "native_rhs_norm": float(native_rhs_norm),
                    "recovery_forward_relative_error": float(forward_relative),
                    "recovery_forward_error_norm": float(forward_error_norm),
                    "storage_reference_norm": float(storage_norm),
                    "same_lu_corrections": correction_history,
                    "same_lu_correction_limit": 3,
                    "native_packed_coefficient_bytes_by_component": packed_bytes_by_component,
                    "native_packed_coefficient_bound_bytes": int(native_owner_bound[
                        "packed_coefficients_peak_bytes_upper"
                    ]),
                    "native_packed_coefficients_within_bound": packed_coefficients_within_bound,
                    "limits": {
                        "condensed_action_rhs_relative": 1.0e-10,
                        "native_volume_residual_relative": 1.0e-10,
                        "recovery_forward_relative": 1.0e-11,
                    },
                    "raw_arrays": saved_arrays,
                    "status": "PASS" if passed else "FAILED_NUMERICAL_GATE",
                }
                _atomic_write_json(case_path, witness)
                witness["case_manifest_path"] = case_path.name
                witness["case_manifest_sha256"] = _file_sha256(case_path)
                witnesses.append(witness)
                if recovered_vec is not None:
                    recovered_vec.destroy()
                    recovered_vec = None
                source_vec.destroy()
                source_vec = None
                del active_input, storage, frozen_rhs, reduced_rhs, reduced_action
                del recovered, native_recovered_action, residual
                del internal_nonzero_counts, b_nonzero_counts, b_norms
                admit(f"v25_witness_{case}_post_release_process_tree_rss", 0)
            except Exception as error:
                if recovered_vec is not None:
                    recovered_vec.destroy()
                    recovered_vec = None
                if source_vec is not None:
                    source_vec.destroy()
                    source_vec = None
                failure = {
                    "schema": "task40extra.review_v25_complete_target_volume_witness.v1",
                    "case": int(case),
                    "status": "FAILED_WITNESS_WITH_PARTIAL_RAW_EVIDENCE",
                    "failure_type": type(error).__name__,
                    "failure_message": f"{type(error).__name__}: {error}",
                    "raw_arrays_saved_before_failure": saved_arrays,
                }
                _atomic_write_json(case_path, failure)
                raise

        status = (
            "PASS_COMPLETE_TARGET_VOLUME_ACTION"
            if len(witnesses) == 2 and all(row["status"] == "PASS" for row in witnesses)
            else "FAILED_COMPLETE_TARGET_VOLUME_ACTION"
        )
        return {
            "schema": "task40extra.review_v25_complete_target_volume_action.v1",
            "status": status,
            "official_result": False,
            "full_q_matrix": False,
            "q_csr_created": False,
            "factor_created": False,
            "ksp_created": False,
            "pde_solved": False,
            "official_R_T_A_created": False,
            "target_model": {
                "global_cell_axes": list(map(int, cfg.mesh_axis_cell_counts_requested)),
                "cell_count": cell_count,
                "p6_local_cell_dofs": 882,
                "full_storage_rows": full_rows,
                "independent_rows": int(full_rows - len(slave_rows)),
                "trace_rows": int(condensed.trace_rows),
                "active_trace_rows": int(condensed.active_rows),
                "mpc_slave_rows": int(condensed.trace_constraints.slave_rows),
                "mpc_slave_rows_sha256": _array_sha256(np.asarray(slave_rows, dtype="<i8")),
            },
            "form": {
                "components": ["actual_curl_curl", "actual_complex_material_mass"],
                "combined_before_local_schur": True,
                "native_action": dict(native_action.audit),
            },
            "condensation": {
                "global_matrix_materialized": condensed.matrix is not None,
                "global_q_csr_materialized": False,
                "build_audit": dict(condensed.build_audit),
                "trace_constraint_audit": dict(condensed.trace_constraints.build_audit),
                "compact_map_preflight": dict(map_audit),
            },
            "p6_action_owner": {
                "construction": "S-only P6CellCondensedAction; zero carrier ports",
                "preflight": owner_bound,
                "admission": owner_admission,
                "buffer_inventory": dict(p6_action.buffer_inventory),
                "action_audit": dict(p6_action.audit),
            },
            "native_action_owner": {
                "preflight": native_owner_bound,
                "pre_condensation_admission": native_owner_preflight,
                "admission": native_owner_admission,
                "retained_payload_audit": dict(native_action.audit),
            },
            "witnesses": witnesses,
            "resource_gates": gates,
            "elapsed_seconds": float(time.perf_counter() - started),
        }
    finally:
        if p6_action is not None:
            p6_action.destroy()
        if condensed is not None:
            condensed.destroy()
        if native_action is not None:
            native_action.destroy()


__all__ = ["VolumeResourceBlocked", "run_complete_target_volume_action"]


class VolumeResourceBlocked(RuntimeError):
    """A pre-allocation V25 disk gate that must remain a controlled stop."""

    def __init__(self, facts: Mapping[str, Any]):
        self.facts = dict(facts)
        super().__init__("V25 target-volume raw evidence disk admission was blocked")
