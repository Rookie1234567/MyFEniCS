# Broad catches synchronize rank-local third-party failures before the next MPI collective.
# Best-effort cleanup catches preserve the original exception during teardown.
# ruff: noqa: BLE001, S110
"""Distributed Stage-B/C coarse correction over economical harmonic columns.

The component consumes the origin-local columns produced by the economical
Maxwell-harmonic preparation.  It owns only the sparse prolongation, coarse
operator, Krylov state, and work vectors; the fine operator and local
impedance action remain borrowed.  Numeric column values move from each patch
origin to the PETSc fine-row owner one patch at a time.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_maxwell_harmonic_coarse import _symbolic_memory_preflight
from .hybrid_maxwell_harmonic_economical import EconomicalMaxwellHarmonicSpace

ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE = (
    "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
)
FINE_LIVE_VECTOR_COUNT = 75
COARSE_LIVE_VECTOR_COUNT = 70
_VECTOR_STORAGE_MULTIPLIER = 2

__all__ = (
    "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE",
    "COARSE_LIVE_VECTOR_COUNT",
    "FINE_LIVE_VECTOR_COUNT",
    "AdaptiveImpedanceStageBCAction",
    "AdaptiveImpedanceStageBCBuildResult",
    "build_adaptive_impedance_stage_bc_action",
)


def _collective_error(
    comm: MPI.Intracomm,
    local_error: str | None,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    first = next((error for error in errors if error is not None), None)
    if first is not None:
        raise RuntimeError(f"{context}: {first}")


def _row_owner(row: int, ranges: tuple[tuple[int, int], ...]) -> int:
    for rank, (first, last) in enumerate(ranges):
        if int(first) <= int(row) < int(last):
            return rank
    raise ValueError(f"fine row {row} is outside PETSc ownership")


def _matrix_info(matrix: PETSc.Mat) -> tuple[int, int]:
    info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
    return int(info.get("nz_used", 0)), int(info.get("memory", 0))


def _local_patch_layout(
    harmonic_space: EconomicalMaxwellHarmonicSpace,
    action: Any,
    comm: MPI.Intracomm,
) -> tuple[
    dict[tuple[int, int], dict[str, Any]],
    tuple[tuple[Any, ...], ...],
]:
    local: dict[tuple[int, int], dict[str, Any]] = {}
    compact: list[tuple[Any, ...]] = []
    local_error: str | None = None
    try:
        if getattr(harmonic_space, "_destroyed", False):
            raise RuntimeError("harmonic columns have already been released")
        records = {
            tuple(int(value) for value in record.patch_id): record
            for record in harmonic_space.local_patch_records
        }
        action_items = {
            tuple(int(value) for value in item["patch_id"]): item
            for item in action.patch_metadata()
        }
        if set(records) != set(action_items):
            raise ValueError("harmonic-space and action patch IDs differ")
        for patch_id in sorted(records):
            if int(patch_id[0]) != comm.rank:
                raise ValueError("harmonic patch origin differs from local rank")
            record = records[patch_id]
            item = action_items[patch_id]
            rows = tuple(int(value) for value in record.rows)
            if not rows or tuple(sorted(set(rows))) != rows:
                raise ValueError("harmonic patch rows must be sorted and unique")
            weights = np.asarray(record.weights, dtype=np.float64)
            columns = record.columns
            if (
                weights.shape != (len(rows),)
                or columns is None
                or np.asarray(columns).shape[0] != len(rows)
            ):
                raise ValueError("harmonic patch columns and weights have wrong shape")
            columns = np.asarray(columns, dtype=PETSc.ScalarType)
            if (
                columns.ndim != 2
                or not columns.shape[1]
                or columns.shape[1] > len(rows)
            ):
                raise ValueError("harmonic patch selected-column count is invalid")
            if not np.all(np.isfinite(columns)) or not np.all(np.isfinite(weights)):
                raise ValueError("harmonic patch numeric columns are non-finite")
            action_rows = tuple(int(value) for value in item["rows"])
            action_weights = np.asarray(item["weights"], dtype=np.float64)
            if action_rows != rows or not np.array_equal(action_weights, weights):
                raise ValueError("harmonic patch rows or PoU weights differ from action")
            class_key = str(item["class_key"])
            owner_rank = int(item["owner_rank"])
            selected = int(columns.shape[1])
            retained = record.audit.get("retained_rank")
            if retained is not None and int(retained) != selected:
                raise ValueError("harmonic selected rank differs from its audit")
            local[patch_id] = {
                "record": record,
                "rows": rows,
                "weights": weights,
                "columns": columns,
                "class_key": class_key,
                "owner_rank": owner_rank,
                "selected": selected,
            }
            compact.append(
                (patch_id, int(record.cell_index), rows, selected)
            )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "Stage-B/C local patch layout")
    packets = comm.allgather(tuple(compact))
    global_metadata = tuple(
        sorted(
            (item for packet in packets for item in packet),
            key=lambda item: tuple(item[0]),
        )
    )
    if len({tuple(item[0]) for item in global_metadata}) != len(global_metadata):
        raise ValueError("harmonic patch metadata has duplicate IDs")
    if any(
        int(item[0][0]) < 0 or int(item[0][0]) >= comm.size
        for item in global_metadata
    ):
        raise ValueError("harmonic patch origin is outside the communicator")
    return local, global_metadata


def _column_layout(
    metadata: tuple[tuple[Any, ...], ...],
    size: int,
) -> tuple[dict[tuple[int, int], tuple[int, int]], tuple[tuple[int, int], ...]]:
    ranges: list[tuple[int, int]] = []
    counts = [
        sum(int(item[3]) for item in metadata if int(item[0][0]) == rank)
        for rank in range(size)
    ]
    cursor = 0
    for count in counts:
        ranges.append((cursor, cursor + count))
        cursor += count
    patch_ranges: dict[tuple[int, int], tuple[int, int]] = {}
    expected = list(ranges)
    for item in metadata:
        patch_id = tuple(int(value) for value in item[0])
        origin = int(patch_id[0])
        start, stop = expected[origin]
        patch_ranges[patch_id] = (start, start + int(item[3]))
        expected[origin] = (start + int(item[3]), stop)
    if any(start != stop for start, stop in expected):
        raise ValueError("coarse prefix ownership is not deterministic")
    return patch_ranges, tuple(ranges)


def _vector_budget(
    fine_global: int,
    coarse_global: int,
) -> tuple[int, int]:
    scalar_bytes = int(np.dtype(PETSc.ScalarType).itemsize)
    fine = (
        _VECTOR_STORAGE_MULTIPLIER
        * int(fine_global)
        * scalar_bytes
        * FINE_LIVE_VECTOR_COUNT
    )
    coarse = (
        _VECTOR_STORAGE_MULTIPLIER
        * int(coarse_global)
        * scalar_bytes
        * COARSE_LIVE_VECTOR_COUNT
    )
    return int(fine), int(coarse)


def _destroy_safely(objects: list[Any]) -> None:
    for obj in objects:
        if obj is None:
            continue
        try:
            obj.destroy()
        except Exception:
            pass


@dataclass
class AdaptiveImpedanceStageBCAction:
    """Borrowed fine/local action with owned sparse coarse correction."""

    _fine_operator: PETSc.Mat
    _local_action: Any
    _prolongation: PETSc.Mat
    _coarse_matrix: PETSc.Mat
    _coarse_ksp: PETSc.KSP
    _fine_work: tuple[PETSc.Vec, ...]
    _coarse_rhs: PETSc.Vec
    _coarse_solution: PETSc.Vec
    _coarse_residual: PETSc.Vec
    _diagnostics: dict[str, Any]
    _destroyed: bool = False

    @property
    def prolongation(self) -> PETSc.Mat:
        if self._destroyed:
            raise RuntimeError("Stage-B/C action is destroyed")
        return self._prolongation

    @property
    def coarse_matrix(self) -> PETSc.Mat:
        if self._destroyed:
            raise RuntimeError("Stage-B/C action is destroyed")
        return self._coarse_matrix

    @property
    def diagnostics(self) -> dict[str, Any]:
        result = dict(self._diagnostics)
        result["apply_count"] = int(self._diagnostics.get("apply_count", 0))
        result["local_action_apply_count"] = int(
            self._diagnostics.get("local_action_apply_count", 0)
        )
        result["ksp_history"] = list(self._diagnostics.get("ksp_history", ()))
        result["destroyed"] = bool(self._destroyed)
        return result

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Stage-B/C action is destroyed")
        started = perf_counter()
        comm = self._fine_operator.getComm().tompi4py()
        first, last = map(int, self._fine_operator.getOwnershipRange())
        local_error: str | None = None
        try:
            if tuple(map(int, self._fine_operator.getSize())) != (
                int(source.getSize()),
            ) * 2:
                local_error = "fine operator and source size differ"
            elif int(source.getSize()) != int(target.getSize()):
                local_error = "source and target size differ"
            elif tuple(map(int, source.getOwnershipRange())) != (first, last):
                local_error = "source ownership differs from fine operator"
            elif tuple(map(int, target.getOwnershipRange())) != (first, last):
                local_error = "target ownership differs from fine operator"
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(comm, local_error, "Stage-B/C apply preflight")

        y0, r1, x, r2, post, source_copy = self._fine_work
        source.copy(source_copy)
        self._local_action.apply(source_copy, y0)
        self._fine_operator.mult(y0, r1)
        r1.aypx(PETSc.ScalarType(-1.0), source)
        self._prolongation.multHermitian(r1, self._coarse_rhs)
        self._coarse_solution.set(0.0)
        self._coarse_ksp.solve(self._coarse_rhs, self._coarse_solution)
        reason = int(self._coarse_ksp.getConvergedReason())
        bounded_reasons = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(
                getattr(
                    PETSc.KSP.ConvergedReason,
                    "DIVERGED_MAX_IT",
                    getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3),
                )
            ),
        }
        self._coarse_matrix.mult(
            self._coarse_solution, self._coarse_residual
        )
        self._coarse_residual.axpy(
            PETSc.ScalarType(-1.0), self._coarse_rhs
        )
        coarse_residual = float(self._coarse_residual.norm())
        coarse_rhs_norm = float(self._coarse_rhs.norm())
        coarse_relative_residual = coarse_residual / max(coarse_rhs_norm, 1.0e-300)
        local_finite = bool(
            np.isfinite(coarse_residual)
            and np.isfinite(coarse_rhs_norm)
            and np.isfinite(coarse_relative_residual)
            and np.all(
                np.isfinite(
                    np.asarray(
                        self._coarse_solution.getArray(readonly=True),
                        dtype=PETSc.ScalarType,
                    )
                )
            )
        )
        local_error = (
            f"coarse KSP failed with reason {reason}"
            if reason == 0 or (reason < 0 and reason not in bounded_reasons)
            else None
        )
        _collective_error(comm, local_error, "coarse KSP convergence")
        if not comm.allreduce(local_finite, op=MPI.LAND):
            raise RuntimeError("coarse KSP solution or residual is non-finite")
        self._prolongation.mult(self._coarse_solution, x)
        x.axpy(PETSc.ScalarType(1.0), y0)
        self._fine_operator.mult(x, r2)
        r2.aypx(PETSc.ScalarType(-1.0), source)
        self._local_action.apply(r2, post)
        x.copy(target)
        target.axpy(PETSc.ScalarType(1.0), post)
        if not comm.allreduce(
            bool(np.all(np.isfinite(target.getArray(readonly=True)))), op=MPI.LAND
        ):
            raise RuntimeError("Stage-B/C composite output is non-finite")
        self._diagnostics["apply_count"] = int(
            self._diagnostics.get("apply_count", 0) + 1
        )
        self._diagnostics["local_action_apply_count"] = int(
            self._diagnostics.get("local_action_apply_count", 0) + 2
        )
        self._diagnostics.setdefault("ksp_history", []).append(
            {
                "reason": reason,
                "reason_kind": (
                    "max_it_finite" if reason in bounded_reasons else "converged"
                ),
                "iterations": int(self._coarse_ksp.getIterationNumber()),
                "residual": coarse_residual,
                "rhs_norm": coarse_rhs_norm,
                "relative_residual": coarse_relative_residual,
            }
        )
        self._diagnostics["apply_wall_seconds"] = max(
            float(self._diagnostics.get("apply_wall_seconds", 0.0)),
            float(comm.allreduce(perf_counter() - started, op=MPI.MAX)),
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        _destroy_safely(
            [
                *self._fine_work,
                self._coarse_rhs,
                self._coarse_solution,
                self._coarse_residual,
                self._coarse_ksp,
                self._coarse_matrix,
                self._prolongation,
            ]
        )
        self._diagnostics.update(
            {
                "P_live": False,
                "Ac_live": False,
                "KSP_live": False,
                "destroyed": True,
            }
        )
        self._destroyed = True


@dataclass
class AdaptiveImpedanceStageBCBuildResult:
    """Explicit setup result; resource denial carries no live PETSc action."""

    action: AdaptiveImpedanceStageBCAction | None
    status: str
    diagnostics: dict[str, Any]

    def destroy(self) -> None:
        if self.action is not None:
            self.action.destroy()


def build_adaptive_impedance_stage_bc_action(
    *,
    harmonic_space: EconomicalMaxwellHarmonicSpace,
    action: Any,
    fine_operator: PETSc.Mat,
    current_process_tree_baseline_bytes: int | None = None,
    current_process_tree_baseline_source: str = "unavailable",
    hard_memory_bytes: int | None = None,
    phase_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> AdaptiveImpedanceStageBCBuildResult:
    """Build sparse economical coarse correction after a collective memory gate."""

    if not isinstance(fine_operator, PETSc.Mat):
        raise TypeError("Stage-B/C requires a PETSc fine operator")
    comm = fine_operator.getComm().tompi4py()
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("Stage-B/C requires complex128 PETSc scalars")
    fine_size = tuple(map(int, fine_operator.getSize()))
    if fine_size[0] != fine_size[1]:
        raise ValueError("Stage-B/C fine operator must be square")
    local_data, metadata = _local_patch_layout(harmonic_space, action, comm)
    patch_ranges, coarse_ownership = _column_layout(metadata, comm.size)
    selected_total = sum(int(item[3]) for item in metadata)
    patches = tuple(
        {"patch_id": tuple(item[0]), "rows": tuple(item[2])} for item in metadata
    )
    audits = tuple(
        {
            "patch_id": tuple(item[0]),
            "rows": len(item[2]),
            "retained_rank": int(item[3]),
            "selected_mode_count": int(item[3]),
        }
        for item in metadata
    )
    fine_bytes, coarse_bytes = _vector_budget(fine_size[0], selected_total)
    memory = _symbolic_memory_preflight(
        fine_operator,
        action,
        patches,
        audits,
        comm,
        current_process_tree_baseline_bytes,
        current_process_tree_baseline_source,
        hard_memory_bytes=hard_memory_bytes,
        economical_failure_route=ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE,
        basis_in_live_baseline=True,
        fine_live_vector_bytes=fine_bytes,
        fine_live_vector_count=FINE_LIVE_VECTOR_COUNT,
        coarse_live_vector_bytes=coarse_bytes,
        coarse_live_vector_count=COARSE_LIVE_VECTOR_COUNT,
    )
    base_diagnostics: dict[str, Any] = {
        "schema": "task040.v8.adaptive_impedance_stage_bc.v1",
        "patch_count": len(metadata),
        "selected_mode_count_total": int(selected_total),
        "coarse_column_ownership": tuple(
            (rank, int(start), int(stop))
            for rank, (start, stop) in enumerate(coarse_ownership)
        ),
        "memory_preflight": memory,
        "fixed_live_vector_budget": {
            "fine_count": FINE_LIVE_VECTOR_COUNT,
            "coarse_count": COARSE_LIVE_VECTOR_COUNT,
            "fine_bytes": fine_bytes,
            "coarse_bytes": coarse_bytes,
            "storage_multiplier": _VECTOR_STORAGE_MULTIPLIER,
        },
        "full_vector_numeric_allgather": False,
        "full_basis_numeric_replica": False,
        "global_dense_direct_factor": False,
        "harmonic_columns_consumed": False,
        "allocated_object_count": {"P": 0, "P_H": 0, "FP": 0, "Ac": 0, "KSP": 0},
    }

    def emit_phase(
        name: str,
        matrix: PETSc.Mat,
        phase_wall_seconds: float,
        **detail: Any,
    ) -> None:
        if phase_callback is None:
            return
        global_rows, global_columns = map(int, matrix.getSize())
        local_rows, local_columns = map(int, matrix.getLocalSize())
        actual_nnz, actual_memory = _matrix_info(matrix)
        payload = {
            "name": name,
            "global_size": (global_rows, global_columns),
            "local_size": (local_rows, local_columns),
            "global_rows": global_rows,
            "global_columns": global_columns,
            "local_rows": local_rows,
            "local_columns": local_columns,
            "actual_global_nnz": actual_nnz,
            "actual_global_memory_bytes": actual_memory,
            "phase_wall_seconds": float(phase_wall_seconds),
            **detail,
        }
        base_diagnostics.setdefault("phase_diagnostics", {})[name] = payload
        phase_callback(name, payload)

    if not memory["allocation_allowed"]:
        base_diagnostics["status"] = ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE
        base_diagnostics["caller_must_destroy_harmonic_space"] = True
        return AdaptiveImpedanceStageBCBuildResult(
            None,
            ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE,
            base_diagnostics,
        )

    row_ranges = tuple(
        (int(first), int(last))
        for first, last in comm.allgather(fine_operator.getOwnershipRange())
    )
    row_to_patches: dict[int, list[tuple[int, int]]] = {}
    for item in metadata:
        patch_id = tuple(int(value) for value in item[0])
        for row in item[2]:
            row_to_patches.setdefault(int(row), []).append(patch_id)
    first, last = map(int, fine_operator.getOwnershipRange())
    local_rows = last - first
    local_start, local_stop = coarse_ownership[comm.rank]
    diag_nnz = np.zeros(local_rows, dtype=PETSc.IntType)
    offdiag_nnz = np.zeros(local_rows, dtype=PETSc.IntType)
    selected_by_id = {tuple(item[0]): int(item[3]) for item in metadata}
    for row in range(first, last):
        for patch_id in row_to_patches.get(row, ()):
            if int(patch_id[0]) == comm.rank:
                diag_nnz[row - first] += selected_by_id[patch_id]
            else:
                offdiag_nnz[row - first] += selected_by_id[patch_id]
    preallocation = (
        diag_nnz if comm.size == 1 else (diag_nnz, offdiag_nnz)
    )
    prolongation: PETSc.Mat | None = None
    ph: PETSc.Mat | None = None
    fine_times_p: PETSc.Mat | None = None
    coarse_matrix: PETSc.Mat | None = None
    coarse_ksp: PETSc.KSP | None = None
    fine_work: list[PETSc.Vec] = []
    coarse_rhs = None
    coarse_solution = None
    coarse_residual = None
    columns_released = False
    try:
        p_started = perf_counter()
        prolongation = PETSc.Mat().createAIJ(
            size=((local_rows, fine_size[0]), (local_stop - local_start, selected_total)),
            nnz=preallocation,
            comm=comm,
        )
        prolongation.setOption(
            PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR,
            True,
        )
        max_sender = 0
        max_receiver = 0
        max_single = 0
        numeric_collective_count = 0
        for item in metadata:
            patch_id = tuple(int(value) for value in item[0])
            rows = tuple(int(value) for value in item[2])
            selected = int(item[3])
            start, stop = patch_ranges[patch_id]
            outgoing: list[list[tuple[Any, ...]]] = [
                [] for _ in range(comm.size)
            ]
            sender_bytes = 0
            local_error: str | None = None
            try:
                if comm.rank == int(patch_id[0]):
                    local_patch = local_data.get(patch_id)
                    if local_patch is None:
                        raise RuntimeError("patch origin lacks harmonic columns")
                    by_destination: dict[int, list[int]] = {}
                    for position, row in enumerate(rows):
                        destination = _row_owner(row, row_ranges)
                        by_destination.setdefault(destination, []).append(position)
                    for destination, positions in by_destination.items():
                        packet_rows = np.asarray(
                            [rows[position] for position in positions],
                            dtype=PETSc.IntType,
                        )
                        packet_values = np.empty(
                            (len(positions), selected), dtype=PETSc.ScalarType
                        )
                        for packet_position, position in enumerate(positions):
                            packet_values[packet_position, :] = (
                                local_patch["weights"][position]
                                * local_patch["columns"][position, :]
                            )
                        sender_bytes += int(packet_rows.nbytes + packet_values.nbytes)
                        outgoing[destination].append(
                            (patch_id, packet_rows, int(start), packet_values)
                        )
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _collective_error(comm, local_error, "Stage-B/C P packet construction")
            incoming = comm.alltoall(outgoing)
            numeric_collective_count += 1
            max_sender = max(max_sender, sender_bytes)
            received: list[tuple[np.ndarray, np.ndarray, int]] = []
            local_error: str | None = None
            try:
                for packet_list in incoming:
                    for received_id, packet_rows, column_start, values in packet_list:
                        if tuple(received_id) != patch_id:
                            raise RuntimeError("P received an unknown patch packet")
                        packet_rows = np.asarray(packet_rows, dtype=PETSc.IntType)
                        values = np.asarray(values, dtype=PETSc.ScalarType)
                        if (
                            packet_rows.ndim != 1
                            or values.shape != (len(packet_rows), selected)
                            or not np.all(np.isfinite(values))
                            or any(not first <= int(row) < last for row in packet_rows)
                            or int(column_start) != int(start)
                        ):
                            raise ValueError("P received an invalid patch packet")
                        received.append((packet_rows, values, int(column_start)))
                receiver_bytes = sum(
                    int(rows.nbytes + values.nbytes)
                    for rows, values, _ in received
                )
                max_receiver = max(max_receiver, receiver_bytes)
                max_single = max(max_single, sender_bytes, receiver_bytes)
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _collective_error(comm, local_error, "Stage-B/C P packet validation")
            local_error = None
            try:
                columns = np.arange(start, stop, dtype=PETSc.IntType)
                for packet_rows, values, _column_start in received:
                    for row, value in zip(packet_rows, values, strict=True):
                        prolongation.setValues(int(row), columns, value)
            except Exception as exc:
                local_error = f"{type(exc).__name__}: {exc}"
            _collective_error(comm, local_error, "Stage-B/C P local insertion")
        prolongation.assemblyBegin()
        prolongation.assemblyEnd()
        if phase_callback is not None:
            p_wall = float(
                comm.allreduce(perf_counter() - p_started, op=MPI.MAX)
            )
            emit_phase("P_ready", prolongation, p_wall)
        harmonic_space.destroy()
        columns_released = True

        ph_started = perf_counter()
        ph = PETSc.Mat()
        prolongation.hermitianTranspose(ph)
        if phase_callback is not None:
            ph_wall = float(
                comm.allreduce(perf_counter() - ph_started, op=MPI.MAX)
            )
            emit_phase("P_H_ready", ph, ph_wall)

        fp_started = perf_counter()
        fine_times_p = fine_operator.matMult(prolongation)
        if phase_callback is not None:
            fp_wall = float(
                comm.allreduce(perf_counter() - fp_started, op=MPI.MAX)
            )
            emit_phase("FP_ready", fine_times_p, fp_wall)

        ac_started = perf_counter()
        coarse_matrix = ph.matMult(fine_times_p)
        coarse_matrix.assemble()
        if phase_callback is not None:
            ac_wall = float(
                comm.allreduce(perf_counter() - ac_started, op=MPI.MAX)
            )
            emit_phase("Ac_ready", coarse_matrix, ac_wall)
        ph.destroy()
        ph = None
        fine_times_p.destroy()
        fine_times_p = None

        ksp_started = perf_counter()
        coarse_ksp = PETSc.KSP().create(comm=comm)
        coarse_ksp.setOperators(coarse_matrix)
        coarse_ksp.setType(PETSc.KSP.Type.GMRES)
        coarse_ksp.setGMRESRestart(32)
        coarse_ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=32)
        coarse_ksp.setInitialGuessNonzero(False)
        coarse_ksp.getPC().setType(PETSc.PC.Type.JACOBI)
        coarse_ksp.setUp()
        fine_work = [fine_operator.createVecRight() for _ in range(6)]
        coarse_rhs = prolongation.createVecRight()
        coarse_solution = prolongation.createVecRight()
        coarse_residual = prolongation.createVecRight()
        if phase_callback is not None:
            ksp_wall = float(
                comm.allreduce(perf_counter() - ksp_started, op=MPI.MAX)
            )
            emit_phase(
                "coarse_ksp_ready",
                coarse_matrix,
                ksp_wall,
                ksp={
                    "type": "gmres",
                    "restart": 32,
                    "rtol": 1.0e-6,
                    "atol": 0.0,
                    "max_it": 32,
                    "zero_initial_guess": True,
                    "pc": "jacobi",
                    "set_from_options": False,
                },
            )
        p_nnz, p_bytes = _matrix_info(prolongation)
        ac_nnz, ac_bytes = _matrix_info(coarse_matrix)
        base_diagnostics.update(
            {
                "status": "ready",
                "coarse_column_ranges": {
                    str(patch_id): tuple(map(int, bounds))
                    for patch_id, bounds in patch_ranges.items()
                },
                "P_nnz": p_nnz,
                "P_bytes": p_bytes,
                "Ac_nnz": ac_nnz,
                "Ac_bytes": ac_bytes,
                "numeric_object_alltoall_count": numeric_collective_count,
                "max_sender_payload_bytes": int(
                    comm.allreduce(max_sender, op=MPI.MAX)
                ),
                "max_receiver_payload_bytes": int(
                    comm.allreduce(max_receiver, op=MPI.MAX)
                ),
                "max_single_patch_payload_bytes": int(
                    comm.allreduce(max_single, op=MPI.MAX)
                ),
                "numeric_collective_type": (
                    "one bounded origin-to-fine-row-owner object alltoall per patch"
                ),
                "numeric_payload_bound": (
                    "sender/receiver aggregate is bounded by one patch packet "
                    "(row indices plus values)"
                ),
                "transient_matrices_released": {"P_H": True, "F_times_P": True},
                "harmonic_columns_consumed": columns_released,
                "allocated_object_count": {"P": 1, "P_H": 0, "FP": 0, "Ac": 1, "KSP": 1},
                "ksp": {
                    "type": "gmres",
                    "restart": 32,
                    "rtol": 1.0e-6,
                    "atol": 0.0,
                    "max_it": 32,
                    "zero_initial_guess": True,
                    "pc": "jacobi",
                    "set_from_options": False,
                },
            }
        )
        coarse_action = AdaptiveImpedanceStageBCAction(
            fine_operator,
            action,
            prolongation,
            coarse_matrix,
            coarse_ksp,
            tuple(fine_work),
            coarse_rhs,
            coarse_solution,
            coarse_residual,
            base_diagnostics,
        )
        return AdaptiveImpedanceStageBCBuildResult(
            coarse_action,
            "ready",
            base_diagnostics,
        )
    except Exception:
        _destroy_safely(
            [
                *fine_work,
                coarse_rhs,
                coarse_solution,
                coarse_residual,
                coarse_ksp,
                coarse_matrix,
                fine_times_p,
                ph,
                prolongation,
            ]
        )
        if not columns_released:
            try:
                harmonic_space.destroy()
            except Exception:
                pass
        raise
