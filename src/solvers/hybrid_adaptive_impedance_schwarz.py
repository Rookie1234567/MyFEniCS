# Broad catches synchronize rank-local third-party failures before the next MPI collective.
# ruff: noqa: BLE001
"""Bounded owner-local impedance Schwarz pilot for Task040.

This module is deliberately a component, not a route or a parameter scan.
The caller supplies one raw H(curl) tangential face-mass block per owned cell;
the block is reduced with the existing trace expansion as ``C^H M_t C``.
The outer bare-F matrix is borrowed and is never changed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_adaptive_impedance_mass import ActualHcurlCellTangentialMassProvider
from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from .hybrid_side_impedance import _petsc_matrix_hash
from .static_local_schur_action import iter_owned_constrained_schur_contributions

MAX_LOCAL_ACTIVE_ROWS = 1024
PC_ONLY_ABSORPTION_SHIFT = 0.1

__all__ = (
    "MAX_LOCAL_ACTIVE_ROWS",
    "PC_ONLY_ABSORPTION_SHIFT",
    "AdaptiveImpedanceSchwarzAction",
    "AdaptiveImpedanceSchwarzPlan",
    "build_adaptive_impedance_schwarz_action",
    "reduce_cell_tangential_face_mass",
)


def _row_ranges(matrix: PETSc.Mat) -> tuple[tuple[int, int], ...]:
    first, last = map(int, matrix.getOwnershipRange())
    return tuple(matrix.getComm().tompi4py().allgather((first, last)))


def _row_owner(row: int, ranges: tuple[tuple[int, int], ...]) -> int:
    for rank, (first, last) in enumerate(ranges):
        if first <= int(row) < last:
            return rank
    raise ValueError(f"active row {row} is outside all PETSc ownership ranges")


def _local_matrix_array(matrix: Any, size: int) -> np.ndarray:
    if isinstance(matrix, PETSc.Mat):
        if tuple(map(int, matrix.getSize())) != (size, size):
            raise ValueError("cell face mass size does not match raw cell trace")
        rows = np.arange(size, dtype=PETSc.IntType)
        values = np.asarray(matrix.getValues(rows, rows), dtype=np.complex128)
    else:
        values = np.asarray(matrix, dtype=np.complex128)
    if values.shape != (size, size):
        raise ValueError("cell face mass must be a square raw local block")
    if not np.all(np.isfinite(values)):
        raise ValueError("cell tangential face mass is non-finite")
    return np.ascontiguousarray(values)


def _raw_mass_fingerprint(values: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(np.asarray(values.shape, dtype="<i8").tobytes())
    digest.update(np.asarray(values, dtype="<c16").tobytes())
    return digest.hexdigest()


def _fixed_shift_values(diagonal: np.ndarray, global_max_diag: float) -> np.ndarray:
    floor = 1.0e-12 * float(global_max_diag)
    return -1j * PC_ONLY_ABSORPTION_SHIFT * np.maximum(
        np.abs(np.asarray(diagonal, dtype=np.complex128)), floor
    )


def reduce_cell_tangential_face_mass(
    condensed: Any,
    cell_index: int,
    raw_face_mass: Any,
    *,
    audit_cache: dict[str, tuple[float, float]] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Reduce one caller-assembled cell face mass through the trace constraints.

    ``raw_face_mass`` must be the complete tangential mass on all cut faces of
    this cell, in ``cell_recovery_maps[cell_index].trace_original_dofs`` order.
    It is intentionally a local block; no global or replicated mass is made.
    """

    cell = condensed.cell_recovery_maps[int(cell_index)]
    raw_rows = tuple(int(row) for row in cell.trace_original_dofs)
    if not raw_rows or len(set(raw_rows)) != len(raw_rows):
        raise ValueError("cell tangential face mass has invalid raw trace support")
    constraints = condensed.trace_constraints.expansion_by_original
    if any(row not in constraints for row in raw_rows):
        raise ValueError("cell tangential face mass has an unknown trace row")
    active = sorted(
        {
            int(active_row)
            for row in raw_rows
            for active_row, coefficient in zip(
                constraints[row][0], constraints[row][1], strict=True
            )
            if coefficient != 0
        }
    )
    active_ids = np.asarray(active, dtype=PETSc.IntType)
    positions = {row: index for index, row in enumerate(active)}
    expansion = np.zeros((len(raw_rows), len(active)), dtype=np.complex128)
    for raw_position, row in enumerate(raw_rows):
        active_rows, coefficients = constraints[row]
        for active_row, coefficient in zip(active_rows, coefficients, strict=True):
            expansion[raw_position, positions[int(active_row)]] = coefficient
    raw = _local_matrix_array(raw_face_mass, len(raw_rows))
    mass_key = _raw_mass_fingerprint(raw)
    cached_audit = None if audit_cache is None else audit_cache.get(mass_key)
    if cached_audit is None:
        scale = max(float(np.linalg.norm(raw)), 1.0e-300)
        hermitian_defect = float(np.linalg.norm(raw - raw.conj().T) / scale)
        if hermitian_defect > 1.0e-10:
            raise ValueError(
                "cell tangential face mass is not Hermitian: "
                f"defect={hermitian_defect:.3e}"
            )
        eigenvalues = np.linalg.eigvalsh((raw + raw.conj().T) * 0.5)
        minimum_eigenvalue = float(np.min(eigenvalues, initial=0.0))
        if minimum_eigenvalue < -1.0e-10 * scale:
            raise ValueError(
                "cell tangential face mass is not positive semidefinite: "
                f"minimum_eigenvalue={minimum_eigenvalue:.3e}"
            )
        if audit_cache is not None:
            audit_cache[mass_key] = (hermitian_defect, minimum_eigenvalue)
    else:
        hermitian_defect, minimum_eigenvalue = cached_audit
    reduced = np.asarray(
        expansion.conj().T @ raw @ expansion,
        dtype=np.complex128,
    )
    reduced_scale = max(float(np.linalg.norm(reduced)), 1.0e-300)
    reduced_support = np.any(np.abs(reduced) > 1.0e-14, axis=1)
    if (
        not np.all(np.isfinite(reduced))
        or reduced_scale <= 1.0e-300
        or not np.all(reduced_support)
    ):
        raise ValueError("reduced cell tangential face mass is empty or non-finite")
    return active_ids, reduced, {
        "source": "caller_declared_real_hcurl_tangential_trace_mass",
        "actual_hcurl_facet_form_assembler": "not_implemented_by_component",
        "reduction": "C^H_M_t_C",
        "raw_mass_fingerprint": mass_key,
        "raw_rows": len(raw_rows),
        "reduced_rows": len(active_ids),
        "raw_finite": True,
        "raw_hermitian_psd": True,
        "raw_hermitian_relative_defect": hermitian_defect,
        "raw_minimum_eigenvalue": minimum_eigenvalue,
        "reduced_finite": True,
        "reduced_nonzero": True,
        "reduced_support_complete": bool(np.all(reduced_support)),
        "residual_ratio_kind": "fixed_setup_probe_before_matrix_release",
    }


def _fetch_vec_values(
    vector: PETSc.Vec,
    patch_rows: tuple[np.ndarray, ...],
    ranges: tuple[tuple[int, int], ...],
) -> tuple[np.ndarray, ...]:
    """Fetch only requested owner rows with two bounded object Alltoall phases."""

    comm = vector.getComm().tompi4py()
    requests: list[list[tuple[int, int]]] = [[] for _ in range(comm.size)]
    for patch_index, rows in enumerate(patch_rows):
        for row in rows:
            requests[_row_owner(int(row), ranges)].append((patch_index, int(row)))
    incoming = comm.alltoall(requests)
    first, last = map(int, vector.getOwnershipRange())
    local_values = vector.getArray(readonly=True)
    responses: list[list[tuple[int, int, complex]]] = [[] for _ in range(comm.size)]
    for requester, packet in enumerate(incoming):
        responses[requester] = [
            (patch_index, row, complex(local_values[row - first]))
            for patch_index, row in packet
            if first <= row < last
        ]
    returned = comm.alltoall(responses)
    result = [np.zeros(len(rows), dtype=PETSc.ScalarType) for rows in patch_rows]
    filled = [np.zeros(len(rows), dtype=bool) for rows in patch_rows]
    for packet in returned:
        for patch_index, row, value in packet:
            rows = patch_rows[patch_index]
            position = int(np.searchsorted(rows, row))
            if position >= len(rows) or int(rows[position]) != row:
                raise RuntimeError("owner row response does not match patch request")
            result[patch_index][position] = PETSc.ScalarType(value)
            filled[patch_index][position] = True
    if any(not np.all(slots) for slots in filled):
        raise RuntimeError("owner row response left a requested diagonal slot empty")
    return tuple(result)


def _owner_multiplicity(
    patch_rows: tuple[np.ndarray, ...],
    ranges: tuple[tuple[int, int], ...],
    comm: MPI.Intracomm,
) -> tuple[tuple[np.ndarray, ...], dict[int, int], dict[int, float]]:
    contributions: list[list[int]] = [[] for _ in range(comm.size)]
    for rows in patch_rows:
        for row in rows:
            contributions[_row_owner(int(row), ranges)].append(int(row))
    incoming = comm.alltoall(contributions)
    owned_counts: dict[int, int] = {}
    for packet in incoming:
        for row in packet:
            owned_counts[row] = owned_counts.get(row, 0) + 1
    requests: list[list[tuple[int, int]]] = [[] for _ in range(comm.size)]
    for patch_index, rows in enumerate(patch_rows):
        for row in rows:
            requests[_row_owner(int(row), ranges)].append((patch_index, int(row)))
    returned = comm.alltoall(requests)
    responses: list[list[tuple[int, int, int]]] = [[] for _ in range(comm.size)]
    for requester, packet in enumerate(returned):
        responses[requester] = [
            (patch_index, row, owned_counts[row]) for patch_index, row in packet
        ]
    received = comm.alltoall(responses)
    weights = [np.zeros(len(rows), dtype=np.float64) for rows in patch_rows]
    filled = [np.zeros(len(rows), dtype=bool) for rows in patch_rows]
    for packet in received:
        for patch_index, row, count in packet:
            if count <= 0:
                raise RuntimeError("patch multiplicity is not positive")
            position = int(np.searchsorted(patch_rows[patch_index], row))
            weights[patch_index][position] = 1.0 / count
            filled[patch_index][position] = True
    if any(not np.all(slots) for slots in filled):
        raise RuntimeError("owner multiplicity response left a weight slot empty")
    weighted_contributions: list[list[tuple[int, float]]] = [
        [] for _ in range(comm.size)
    ]
    for rows, slots in zip(patch_rows, weights, strict=True):
        for row, weight in zip(rows, slots, strict=True):
            weighted_contributions[_row_owner(int(row), ranges)].append(
                (int(row), float(weight))
            )
    weighted_incoming = comm.alltoall(weighted_contributions)
    owned_weight_sums: dict[int, float] = {}
    for packet in weighted_incoming:
        for row, weight in packet:
            owned_weight_sums[row] = owned_weight_sums.get(row, 0.0) + weight
    return tuple(weights), owned_counts, owned_weight_sums


def _row_count_statistics(
    patch_rows: tuple[np.ndarray, ...],
    comm: MPI.Intracomm,
) -> tuple[int, float, int, dict[str, int]]:
    histogram = np.zeros(MAX_LOCAL_ACTIVE_ROWS + 1, dtype=np.int64)
    for rows in patch_rows:
        count = len(rows)
        if count > MAX_LOCAL_ACTIVE_ROWS:
            raise RuntimeError("patch row histogram received an over-cap entry")
        histogram[count] += 1
    global_histogram = np.zeros_like(histogram)
    comm.Allreduce(histogram, global_histogram, op=MPI.SUM)
    nonzero = np.flatnonzero(global_histogram)
    if nonzero.size == 0:
        return 0, 0.0, 0, {}
    total = int(np.sum(global_histogram))
    minimum = int(nonzero[0])
    maximum = int(nonzero[-1])
    target = (total - 1) // 2
    cumulative = 0
    median = minimum
    for count in nonzero:
        cumulative += int(global_histogram[count])
        if cumulative > target:
            median = int(count)
            break
    return minimum, float(median), maximum, {
        str(int(count)): int(global_histogram[count]) for count in nonzero
    }


def _collective_error(
    comm: MPI.Intracomm,
    local_error: str | None,
    context: str,
) -> None:
    errors = comm.allgather(local_error)
    first = next((error for error in errors if error is not None), None)
    if first is not None:
        raise RuntimeError(f"{context}: {first}")


def _matrix_fingerprint(matrix: PETSc.Mat) -> str:
    digest = hashlib.sha256()
    size = int(matrix.getSize()[0])
    for row in range(size):
        columns, values = matrix.getRow(row)
        digest.update(np.asarray([row], dtype="<i8").tobytes())
        digest.update(np.asarray(columns, dtype="<i8").tobytes())
        digest.update(np.asarray(values, dtype=np.complex128).tobytes())
    return digest.hexdigest()


def _matrix_bytes(matrix: PETSc.Mat) -> int:
    info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    return int(info.get("memory", info.get("nz_used", 0) * 24))


def _make_patch_matrix(
    rows: np.ndarray,
    volume_rows: np.ndarray,
    volume: np.ndarray,
    mass_rows: np.ndarray,
    mass: np.ndarray,
    diagonal: np.ndarray,
    global_max_diag: float,
    beta: complex,
) -> PETSc.Mat:
    size = len(rows)
    position = {int(row): index for index, row in enumerate(rows)}
    values = np.zeros((size, size), dtype=np.complex128)
    volume_positions = np.asarray([position[int(row)] for row in volume_rows])
    mass_positions = np.asarray([position[int(row)] for row in mass_rows])
    values[np.ix_(volume_positions, volume_positions)] += volume
    values[np.ix_(mass_positions, mass_positions)] += -1j * complex(beta) * mass
    shift = _fixed_shift_values(diagonal, global_max_diag)
    values[np.arange(size), np.arange(size)] += shift
    if not np.all(np.isfinite(values)):
        raise ValueError("adaptive patch impedance matrix is non-finite")
    matrix = PETSc.Mat().createAIJ(
        size=(size, size),
        nnz=max(1, size),
        comm=PETSc.COMM_SELF,
    )
    matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    matrix.setValues(
        np.arange(size, dtype=PETSc.IntType),
        np.arange(size, dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


@dataclass
class _Patch:
    patch_id: tuple[int, int]
    cell_index: int
    rows: np.ndarray
    class_key: str
    owner_rank: int
    weights: np.ndarray


@dataclass
class AdaptiveImpedanceSchwarzPlan:
    """Owner-local patch metadata; numeric arrays are never globally replicated."""

    patches: tuple[_Patch, ...]
    row_ranges: tuple[tuple[int, int], ...]
    diagnostics: dict[str, Any]


@dataclass
class _ClassFactor:
    factor: ResearchExactFactorInverse
    rhs: PETSc.Vec
    solution: PETSc.Vec
    diagnostic_matrix: PETSc.Mat | None
    diagnostic_residual: PETSc.Vec | None
    factor_probe_residual_ratio: float
    factor_bytes: int
    factor_nnz: int


def _destroy_representatives(representatives: Mapping[str, PETSc.Mat]) -> None:
    for matrix in representatives.values():
        matrix.destroy()


def _ratio_summary(
    comm: MPI.Intracomm,
    local_ratios: Mapping[str, float],
) -> dict[str, float | int | None]:
    packets = comm.gather(tuple(float(value) for value in local_ratios.values()), root=0)
    if comm.rank == 0:
        values = np.asarray(
            [value for packet in packets for value in packet], dtype=np.float64
        )
        if values.size:
            summary: dict[str, float | int | None] = {
                "count": int(values.size),
                "min": float(np.min(values)),
                "median": float(np.median(values)),
                "p90": float(np.quantile(values, 0.9)),
                "max": float(np.max(values)),
            }
        else:
            summary = {
                "count": 0,
                "min": None,
                "median": None,
                "p90": None,
                "max": None,
            }
    else:
        summary = {}
    return comm.bcast(summary, root=0)


class AdaptiveImpedanceSchwarzAction:
    """Borrowed bare-F owner-routed bounded patch action."""

    def __init__(
        self,
        bare_f: PETSc.Mat,
        plan: AdaptiveImpedanceSchwarzPlan,
        class_factors: Mapping[str, _ClassFactor],
    ) -> None:
        self._bare_f = bare_f
        self.plan = plan
        self._class_factors = dict(class_factors)
        self._comm = bare_f.getComm().tompi4py()
        self._apply_count = 0
        self._apply_wall_seconds = 0.0
        self._diagnostic_matrices_released = False
        self._last_real_apply_patch_residual_ratios: dict[str, float] = {}
        self._max_sender_payload_bytes = 0
        self._max_single_patch_payload_bytes = 0
        self._max_owner_payload_bytes = 0
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        started = perf_counter()
        local_error: str | None = None
        try:
            expected_range = self.plan.row_ranges[self._comm.rank]
            if self._destroyed:
                local_error = "adaptive impedance Schwarz action is destroyed"
            else:
                bare_size = tuple(map(int, self._bare_f.getSize()))
                if bare_size[0] != bare_size[1]:
                    local_error = "adaptive Schwarz bare F is not square"
                elif int(source.getSize()) != bare_size[1] or int(target.getSize()) != bare_size[0]:
                    local_error = "adaptive Schwarz source/target size differs from bare F"
                elif tuple(map(int, self._bare_f.getOwnershipRange())) != expected_range:
                    local_error = "adaptive Schwarz bare-F ownership differs from plan"
                elif tuple(map(int, source.getOwnershipRange())) != expected_range:
                    local_error = "adaptive Schwarz source ownership differs from plan"
                elif tuple(map(int, target.getOwnershipRange())) != expected_range:
                    local_error = "adaptive Schwarz target ownership differs from plan"
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz apply preflight")
        try:
            source_values = _fetch_vec_values(
                source,
                tuple(patch.rows for patch in self.plan.patches),
                self.plan.row_ranges,
            )
            local_error = None
        except Exception as exc:
            source_values = ()
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz source routing")
        outgoing: list[list[tuple[tuple[int, int], str, np.ndarray]]] = [
            [] for _ in range(self._comm.size)
        ]
        try:
            aggregate_sender = [0] * self._comm.size
            for patch, values in zip(self.plan.patches, source_values, strict=True):
                values = np.asarray(values, dtype=PETSc.ScalarType)
                if values.shape != (len(patch.rows),):
                    raise ValueError("patch source payload has the wrong shape")
                if not np.all(np.isfinite(values)):
                    raise ValueError("patch source payload is non-finite")
                payload_bytes = int(values.nbytes)
                aggregate_sender[patch.owner_rank] += payload_bytes
                self._max_single_patch_payload_bytes = max(
                    self._max_single_patch_payload_bytes, payload_bytes
                )
                outgoing[patch.owner_rank].append(
                    (patch.patch_id, patch.class_key, values.copy())
                )
            self._max_sender_payload_bytes = max(
                self._max_sender_payload_bytes, sum(aggregate_sender)
            )
            local_error = None
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz patch routing")
        incoming = self._comm.alltoall(outgoing)
        responses: list[list[tuple[tuple[int, int], np.ndarray, float | None]]] = [
            [] for _ in range(self._comm.size)
        ]
        local_error = None
        try:
            received_bytes = sum(
                int(np.asarray(values).nbytes)
                for packets in incoming
                for _patch_id, _class_key, values in packets
            )
            self._max_owner_payload_bytes = max(
                self._max_owner_payload_bytes, received_bytes
            )
            for origin, packets in enumerate(incoming):
                for patch_id, class_key, values in packets:
                    class_factor = self._class_factors.get(class_key)
                    if class_factor is None:
                        raise RuntimeError("patch class owner has no exact factor")
                    values = np.asarray(values, dtype=PETSc.ScalarType)
                    if values.shape != class_factor.rhs.array.shape:
                        raise ValueError("patch owner payload has the wrong shape")
                    if not np.all(np.isfinite(values)):
                        raise ValueError("patch owner payload is non-finite")
                    class_factor.rhs.array[:] = np.asarray(
                        values,
                        dtype=PETSc.ScalarType,
                    )
                    class_factor.factor.solve(class_factor.rhs, class_factor.solution)
                    ratio = None
                    if class_factor.diagnostic_matrix is not None:
                        class_factor.diagnostic_matrix.mult(
                            class_factor.solution, class_factor.diagnostic_residual
                        )
                        class_factor.diagnostic_residual.axpy(
                            PETSc.ScalarType(-1.0), class_factor.rhs
                        )
                        ratio = float(class_factor.diagnostic_residual.norm()) / max(
                            float(class_factor.rhs.norm()), 1.0e-300
                        )
                        if not np.isfinite(ratio):
                            raise RuntimeError("patch residual ratio is non-finite")
                    responses[origin].append(
                        (
                            patch_id,
                            np.asarray(
                                class_factor.solution.getArray(readonly=True),
                                dtype=PETSc.ScalarType,
                            ).copy(),
                            ratio,
                        )
                    )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz owner solve")
        returned = self._comm.alltoall(responses)
        patch_by_id = {patch.patch_id: patch for patch in self.plan.patches}
        local_ratios: dict[str, float] = {}
        validated: list[tuple[tuple[int, int], np.ndarray, float | None]] = []
        local_error = None
        try:
            expected_ids = set(patch_by_id)
            seen_ids: set[tuple[int, int]] = set()
            for packets in returned:
                for patch_id, values, ratio in packets:
                    if patch_id not in patch_by_id:
                        raise RuntimeError("adaptive Schwarz response has an unknown patch")
                    if patch_id in seen_ids:
                        raise RuntimeError("adaptive Schwarz response has a duplicate patch")
                    patch = patch_by_id[patch_id]
                    values = np.asarray(values, dtype=PETSc.ScalarType)
                    if values.shape != (len(patch.rows),):
                        raise ValueError("adaptive Schwarz response has the wrong shape")
                    if not np.all(np.isfinite(values)):
                        raise ValueError("adaptive Schwarz response is non-finite")
                    if self._diagnostic_matrices_released:
                        if ratio is not None:
                            ratio = float(ratio)
                    elif ratio is None or not np.isfinite(float(ratio)):
                        raise RuntimeError(
                            "adaptive Schwarz response lacks a finite diagnostic ratio"
                        )
                    elif float(ratio) < 0.0:
                        raise RuntimeError("adaptive Schwarz diagnostic ratio is negative")
                    seen_ids.add(patch_id)
                    validated.append((patch_id, values, ratio))
            missing = expected_ids - seen_ids
            if missing:
                raise RuntimeError(
                    "adaptive Schwarz response is missing patches: "
                    f"{sorted(missing)!r}"
                )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz response validation")
        corrections: list[list[tuple[int, complex]]] = [
            [] for _ in range(self._comm.size)
        ]
        local_error = None
        try:
            aggregate_sender = [0] * self._comm.size
            for patch_id, values, ratio in validated:
                patch = patch_by_id[patch_id]
                if ratio is not None:
                    local_ratios[str(patch_id)] = float(ratio)
                for row, weight, value in zip(
                    patch.rows,
                    patch.weights,
                    values,
                    strict=True,
                ):
                    corrections[_row_owner(int(row), self.plan.row_ranges)].append(
                        (int(row), complex(weight * value))
                    )
                    aggregate_sender[_row_owner(int(row), self.plan.row_ranges)] += np.dtype(
                        np.complex128
                    ).itemsize
            self._max_sender_payload_bytes = max(
                self._max_sender_payload_bytes, sum(aggregate_sender)
            )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz correction preparation")
        local_error = None
        try:
            received = self._comm.alltoall(corrections)
            self._max_owner_payload_bytes = max(
                self._max_owner_payload_bytes,
                sum(
                    len(packets) * np.dtype(np.complex128).itemsize
                    for packets in received
                ),
            )
            first, last = map(int, target.getOwnershipRange())
            for packets in received:
                for row, value in packets:
                    if not first <= row < last:
                        raise RuntimeError(
                            "adaptive Schwarz correction targets a non-owned row"
                        )
                    if not np.isfinite(complex(value)):
                        raise ValueError("adaptive Schwarz correction is non-finite")
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz correction validation")
        local_error = None
        try:
            target_values = target.getArray()
            target_values.fill(0.0)
            for packets in received:
                for row, value in packets:
                    target_values[row - first] += PETSc.ScalarType(value)
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz target local write")
        self._last_real_apply_patch_residual_ratios = (
            {} if self._diagnostic_matrices_released else local_ratios
        )
        self._apply_count += 1
        self._apply_wall_seconds = max(
            self._apply_wall_seconds,
            float(self._comm.allreduce(perf_counter() - started, op=MPI.MAX)),
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        local_factor_count = 0 if self._destroyed else len(self._class_factors)
        factor_count = int(self._comm.allreduce(local_factor_count, op=MPI.SUM))
        local_factor_bytes = (
            0
            if self._destroyed
            else sum(item.factor_bytes for item in self._class_factors.values())
        )
        factor_nnz = int(
            self._comm.allreduce(
                0
                if self._destroyed
                else sum(item.factor_nnz for item in self._class_factors.values()),
                op=MPI.SUM,
            )
        )
        max_sender = int(
            self._comm.allreduce(self._max_sender_payload_bytes, op=MPI.MAX)
        )
        max_owner = int(
            self._comm.allreduce(self._max_owner_payload_bytes, op=MPI.MAX)
        )
        max_payload = max(max_sender, max_owner)
        active_rows = int(self._bare_f.getSize()[0])
        full_numeric_replica = bool(
            self._comm.size > 1
            and self.plan.diagnostics["global_sequential_union"]
            and max_payload >= active_rows * np.dtype(np.complex128).itemsize
        )
        return {
            **self.plan.diagnostics,
            "apply_count": int(self._apply_count),
            "apply_wall_seconds": float(self._apply_wall_seconds),
            "last_real_apply_patch_residual_summary": _ratio_summary(
                self._comm, self._last_real_apply_patch_residual_ratios
            ),
            "last_real_apply_patch_residual_ratios_local": dict(
                self._last_real_apply_patch_residual_ratios
            ),
            "diagnostic_unavailable_after_release": bool(
                self._diagnostic_matrices_released
            ),
            "factor_lifecycle": {
                "factor_count_ready": factor_count,
                "factor_count_expected": int(self.plan.diagnostics["class_count"]),
                "factor_bytes_local": int(local_factor_bytes),
                "factor_nnz_global": factor_nnz,
                "diagnostic_matrices_released": bool(
                    self._diagnostic_matrices_released
                ),
                "destroyed": bool(self._destroyed),
            },
            "bare_f_borrowed": True,
            "global_auxiliary_matrix": False,
            "numeric_collective_type": "bounded_object_alltoall",
            "numeric_object_alltoall_count": int(5 * self._apply_count),
            "max_sender_payload_bytes": max_sender,
            "max_owner_payload_bytes": max_owner,
            "max_single_patch_payload_bytes": int(
                self._comm.allreduce(
                    self._max_single_patch_payload_bytes, op=MPI.MAX
                )
            ),
            "max_numeric_payload_bytes": max_payload,
            "global_sequential_union": False,
            "full_vector_numeric_allgather": False,
            "diagnostic_scalar_gather": True,
            "numeric_target_write_type": "PETSc_local_array",
            "target_assembly_collective": False,
            "full_numeric_replica": full_numeric_replica,
        }

    def release_diagnostic_matrices(self) -> None:
        """Collectively release original class matrices after Stage A diagnostics."""

        state = (bool(self._destroyed), bool(self._diagnostic_matrices_released))
        if any(item != state for item in self._comm.allgather(state)):
            raise RuntimeError(
                "adaptive Schwarz diagnostic release state differs across ranks"
            )
        if self._destroyed or self._diagnostic_matrices_released:
            return
        local_error: str | None = None
        try:
            for item in self._class_factors.values():
                if item.diagnostic_matrix is None or item.diagnostic_residual is None:
                    raise RuntimeError(
                        "diagnostic matrix state is incomplete before release"
                    )
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz diagnostic release")
        local_error = None
        try:
            for item in self._class_factors.values():
                item.diagnostic_matrix.destroy()
                item.diagnostic_matrix = None
                item.diagnostic_residual.destroy()
                item.diagnostic_residual = None
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
        _collective_error(self._comm, local_error, "adaptive Schwarz diagnostic release")
        self._diagnostic_matrices_released = True
        self._last_real_apply_patch_residual_ratios = {}

    def destroy(self) -> None:
        if self._destroyed:
            return
        for item in self._class_factors.values():
            if item.diagnostic_matrix is not None:
                item.diagnostic_matrix.destroy()
            if item.diagnostic_residual is not None:
                item.diagnostic_residual.destroy()
            item.rhs.destroy()
            item.solution.destroy()
            item.factor.destroy()
        self._class_factors.clear()
        self._diagnostic_matrices_released = True
        self._last_real_apply_patch_residual_ratios = {}
        self._destroyed = True


def _mass_for_cell(source: Any, cell_index: int) -> Any:
    if isinstance(source, Mapping):
        value = source.get(int(cell_index))
    elif callable(source):
        value = source(int(cell_index))
    else:
        raise TypeError("tangential face mass input must be a Mapping or provider")
    if value is None:
        raise ValueError(f"missing real tangential face mass for owned cell {cell_index}")
    return value


def _destroy_class_factors(class_factors: Mapping[str, _ClassFactor]) -> None:
    for item in class_factors.values():
        if item.diagnostic_matrix is not None:
            item.diagnostic_matrix.destroy()
        if item.diagnostic_residual is not None:
            item.diagnostic_residual.destroy()
        item.rhs.destroy()
        item.solution.destroy()
        item.factor.destroy()


def build_adaptive_impedance_schwarz_action(
    condensed: Any,
    bare_f: PETSc.Mat,
    *,
    raw_tangential_face_mass_by_cell: Mapping[int, Any] | Callable[[int], Any],
    beta: complex,
) -> AdaptiveImpedanceSchwarzAction:
    """Build bounded one-cell patches from caller-declared real face masses.

    The mass input may be a mapping or a per-cell provider so callers can avoid
    retaining a second dense mass cache.  This component does not assemble the
    H(curl) facet form itself.
    """

    started = perf_counter()
    if not isinstance(bare_f, PETSc.Mat):
        raise TypeError("adaptive Schwarz requires a PETSc bare-F matrix")
    if not np.isfinite(complex(beta)):
        raise ValueError("adaptive Schwarz beta must be finite")
    comm = bare_f.getComm().tompi4py()
    actual_provider = (
        raw_tangential_face_mass_by_cell
        if isinstance(raw_tangential_face_mass_by_cell, ActualHcurlCellTangentialMassProvider)
        else None
    )
    provider_modes = comm.allgather(actual_provider is not None)
    if any(mode != provider_modes[0] for mode in provider_modes):
        raise RuntimeError(
            "adaptive Schwarz exact-provider authority differs across ranks"
        )
    provider_audit = None
    local_error: str | None = None
    try:
        bare_size = tuple(map(int, bare_f.getSize()))
        active_rows = int(condensed.active_rows)
        if bare_size[0] != bare_size[1]:
            local_error = "adaptive Schwarz bare F is not square"
        elif bare_size[0] != active_rows:
            local_error = (
                "adaptive Schwarz bare/condensed active row count mismatch: "
                f"bare={bare_size[0]}, condensed={active_rows}"
            )
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "adaptive Schwarz support preflight")
    bare_hash_before = _petsc_matrix_hash(bare_f)
    ranges = _row_ranges(bare_f)

    local_cell_rows: list[tuple[int, np.ndarray]] = []
    local_error = None
    try:
        for cell_index, active_ids, block in iter_owned_constrained_schur_contributions(
            condensed
        ):
            rows = np.asarray(active_ids, dtype=PETSc.IntType).copy()
            block_values = np.asarray(block, dtype=np.complex128)
            if rows.ndim != 1 or not rows.size:
                raise ValueError(
                    f"cell {cell_index} support must be a non-empty 1-D row array"
                )
            if np.any(np.diff(rows) <= 0):
                raise ValueError(
                    f"cell {cell_index} support must be strictly sorted and unique"
                )
            if int(rows[0]) < 0 or int(rows[-1]) >= active_rows:
                raise ValueError(
                    f"cell {cell_index} support is outside [0,{active_rows})"
                )
            if block_values.shape != (len(rows), len(rows)):
                raise ValueError(
                    f"cell {cell_index} Schur block shape does not match support"
                )
            if not np.all(np.isfinite(block_values)):
                raise ValueError(f"cell {cell_index} Schur block is non-finite")
            local_cell_rows.append((int(cell_index), rows))
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    _collective_error(comm, local_error, "adaptive Schwarz cell contribution scan")
    local_row_max = max((len(rows) for _cell, rows in local_cell_rows), default=0)
    global_row_max = int(comm.allreduce(local_row_max, op=MPI.MAX))
    if global_row_max > MAX_LOCAL_ACTIVE_ROWS:
        raise RuntimeError(
            "adaptive Schwarz patch exceeds fixed active-row cap: "
            f"observed={global_row_max}, cap={MAX_LOCAL_ACTIVE_ROWS}"
        )

    diagonal = bare_f.createVecLeft()
    try:
        bare_f.getDiagonal(diagonal)
        diagonal_values = np.asarray(
            diagonal.getArray(readonly=True), dtype=PETSc.ScalarType
        )
        if not np.all(np.isfinite(diagonal_values)):
            local_error = "distributed bare-F diagonal is non-finite"
        else:
            local_error = None
        local_max_diag = float(np.max(np.abs(diagonal_values), initial=0.0))
    except Exception as exc:
        local_max_diag = 0.0
        local_error = f"{type(exc).__name__}: {exc}"
    finally:
        diagonal.destroy()
    _collective_error(comm, local_error, "adaptive Schwarz bare-F diagonal")
    global_max_diag = float(comm.allreduce(local_max_diag, op=MPI.MAX))

    patch_rows_for_diag = tuple(rows for _cell, rows in local_cell_rows)
    diagonal = bare_f.createVecLeft()
    try:
        bare_f.getDiagonal(diagonal)
        local_diag = _fetch_vec_values(diagonal, patch_rows_for_diag, ranges)
        local_error = None
    except Exception as exc:
        local_diag = ()
        local_error = f"{type(exc).__name__}: {exc}"
    finally:
        diagonal.destroy()
    _collective_error(comm, local_error, "adaptive Schwarz patch diagonal routing")

    representatives: dict[str, PETSc.Mat] = {}
    patch_rows: list[np.ndarray] = []
    patch_ids: list[tuple[int, int]] = []
    class_keys: list[str] = []
    mass_audits_local: dict[str, dict[str, Any]] = {}
    mass_audit_cache: dict[str, tuple[float, float]] = {}
    try:
        contributions = iter_owned_constrained_schur_contributions(condensed)
        for (cell_index, active_ids, block), (expected_cell, rows), diag_values in zip(
            contributions,
            local_cell_rows,
            local_diag,
            strict=True,
        ):
            if int(cell_index) != expected_cell:
                raise RuntimeError("cell contribution order changed during streaming scan")
            if not np.array_equal(np.asarray(active_ids), rows):
                raise RuntimeError("cell contribution support changed during streaming scan")
            raw_mass = _mass_for_cell(raw_tangential_face_mass_by_cell, cell_index)
            mass_rows, reduced_mass, mass_audit = reduce_cell_tangential_face_mass(
                condensed,
                int(cell_index),
                raw_mass,
                audit_cache=mass_audit_cache,
            )
            if not np.isin(mass_rows, active_ids).all():
                raise ValueError(
                    f"cell {cell_index} face-mass support exceeds its constrained Schur support"
                )
            matrix = _make_patch_matrix(
                rows,
                rows,
                np.asarray(block, dtype=np.complex128),
                mass_rows,
                reduced_mass,
                np.asarray(diag_values, dtype=np.complex128),
                global_max_diag,
                beta,
            )
            class_key = _matrix_fingerprint(matrix)
            if class_key in representatives:
                matrix.destroy()
            else:
                representatives[class_key] = matrix
            patch_rows.append(rows)
            patch_ids.append((comm.rank, int(cell_index)))
            class_keys.append(class_key)
            mass_key = str(mass_audit["raw_mass_fingerprint"])
            if mass_key not in mass_audits_local:
                mass_audits_local[mass_key] = {
                    **mass_audit,
                    "usage_count_local": 0,
                    "cut_face_mass_nonzero": True,
                    "principal_submatrix_used": False,
                    "patch_operator_differs_from_bare_principal": "not_evaluated",
                    "fixed_shift_formula": "-1j*0.1*max(abs(F_ii),1e-12*global_max_abs_diag_F)",
                    "fixed_shift": PC_ONLY_ABSORPTION_SHIFT,
                    "volume_source": "one_owned_cell_constrained_schur_contribution",
                }
            mass_audits_local[mass_key]["usage_count_local"] += 1
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    try:
        _collective_error(comm, local_error, "adaptive Schwarz patch construction")
    except RuntimeError:
        _destroy_representatives(representatives)
        if actual_provider is not None:
            actual_provider.release_numeric_cache()
        raise
    if actual_provider is not None:
        provider_error: str | None = None
        try:
            pre_release_audit = actual_provider.collective_audit()
            if pre_release_audit["status"] != "verified_exact_provider":
                raise RuntimeError(
                    "exact H(curl) provider was not fully consumed before release"
                )
            actual_provider.release_numeric_cache()
            provider_audit = actual_provider.collective_audit()
            if (
                provider_audit["status"] != "verified_exact_provider"
                or not provider_audit["numeric_cache_released"]
                or provider_audit["raw_cache_size_local"] != 0
                or provider_audit["oriented_numeric_cache_size_local"] != 0
            ):
                raise RuntimeError(
                    "exact H(curl) provider post-release audit is incomplete"
                )
        except Exception as exc:
            provider_error = f"{type(exc).__name__}: {exc}"
            try:
                actual_provider.release_numeric_cache()
            except Exception as release_exc:
                provider_error += f"; release: {type(release_exc).__name__}: {release_exc}"
        try:
            _collective_error(
                comm,
                provider_error,
                "adaptive Schwarz exact-provider audit/release",
            )
        except RuntimeError:
            _destroy_representatives(representatives)
            actual_provider.destroy()
            raise
        if provider_error is not None:
            _destroy_representatives(representatives)
            actual_provider.destroy()
            raise RuntimeError(provider_error)

    local_classes = tuple(sorted(representatives))
    all_class_keys = comm.allgather(local_classes)
    unique_classes = sorted({key for packet in all_class_keys for key in packet})
    class_owner = {
        key: min(rank for rank, packet in enumerate(all_class_keys) if key in packet)
        for key in unique_classes
    }
    for key in tuple(representatives):
        if class_owner[key] != comm.rank:
            representatives.pop(key).destroy()

    local_error = None
    try:
        patch_weights, _owned_multiplicity, owned_weight_sums = _owner_multiplicity(
            tuple(patch_rows), ranges, comm
        )
    except Exception as exc:
        patch_weights = ()
        _owned_multiplicity = {}
        owned_weight_sums = {}
        local_error = f"{type(exc).__name__}: {exc}"
    try:
        _collective_error(comm, local_error, "adaptive Schwarz PoU routing")
    except RuntimeError:
        _destroy_representatives(representatives)
        raise
    first, last = ranges[comm.rank]
    missing_owned = next(
        (row for row in range(first, last) if row not in owned_weight_sums), None
    )
    local_pou_error = max(
        (abs(value - 1.0) for value in owned_weight_sums.values()), default=0.0
    )
    covered_rows = int(comm.allreduce(len(owned_weight_sums), MPI.SUM))
    active_rows = int(bare_f.getSize()[0])
    pou_error = float(comm.allreduce(local_pou_error, MPI.MAX))
    if missing_owned is not None or covered_rows != active_rows or pou_error > 1.0e-12:
        _destroy_representatives(representatives)
        raise RuntimeError(
            "adaptive Schwarz owner-computed PoU does not cover bare-F rows: "
            f"missing={missing_owned}, covered={covered_rows}/{active_rows}, "
            f"error={pou_error:.3e}"
        )

    local_factor: dict[str, _ClassFactor] = {}
    local_error = None
    current_matrix: PETSc.Mat | None = None
    current_factor: ResearchExactFactorInverse | None = None
    current_rhs: PETSc.Vec | None = None
    current_solution: PETSc.Vec | None = None
    current_residual: PETSc.Vec | None = None
    try:
        for class_key in unique_classes:
            if class_owner[class_key] != comm.rank:
                continue
            current_matrix = representatives.pop(class_key)
            current_rhs = current_matrix.createVecRight()
            current_solution = current_matrix.createVecLeft()
            current_residual = current_matrix.createVecLeft()
            probe = current_rhs.getArray()
            probe[:] = np.asarray(
                1.0 + 0.013 * np.arange(len(probe))
                + 1j * (0.07 - 0.009 * np.arange(len(probe))),
                dtype=PETSc.ScalarType,
            )
            current_factor = ResearchExactFactorInverse(
                current_matrix,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            current_factor.solve(current_rhs, current_solution)
            current_matrix.mult(current_solution, current_residual)
            current_residual.axpy(PETSc.ScalarType(-1.0), current_rhs)
            probe_ratio = float(current_residual.norm()) / max(
                float(current_rhs.norm()), 1.0e-300
            )
            factor_operator = current_factor.operator
            if factor_operator is None:
                raise RuntimeError("factor-only class has no factor operator")
            factor_bytes = _matrix_bytes(factor_operator)
            factor_nnz = int(
                factor_operator.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"]
            )
            current_factor.release_borrowed_matrix()
            local_factor[class_key] = _ClassFactor(
                factor=current_factor,
                rhs=current_rhs,
                solution=current_solution,
                diagnostic_matrix=current_matrix,
                diagnostic_residual=current_residual,
                factor_probe_residual_ratio=probe_ratio,
                factor_bytes=factor_bytes,
                factor_nnz=factor_nnz,
            )
            current_matrix = None
            current_factor = None
            current_rhs = None
            current_solution = None
            current_residual = None
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    if current_residual is not None:
        current_residual.destroy()
    if current_solution is not None:
        current_solution.destroy()
    if current_rhs is not None:
        current_rhs.destroy()
    if current_factor is not None:
        current_factor.destroy()
    if current_matrix is not None:
        current_matrix.destroy()
    _destroy_representatives(representatives)
    factor_errors = comm.allgather(local_error)
    if any(error is not None for error in factor_errors):
        _destroy_class_factors(local_factor)
        raise RuntimeError(
            "adaptive Schwarz exact class factorization failed: "
            + next(error for error in factor_errors if error is not None)
        )

    probe_packets = comm.allgather(
        {key: item.factor_probe_residual_ratio for key, item in local_factor.items()}
    )
    probe_by_class: dict[str, float] = {}
    local_error = None
    try:
        for packet in probe_packets:
            probe_by_class.update(
                {key: float(value) for key, value in packet.items()}
            )
        for class_key in unique_classes:
            ratio = probe_by_class.get(class_key)
            if ratio is None or not np.isfinite(ratio):
                local_error = f"missing/non-finite factor probe for class {class_key}"
                break
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"
    try:
        _collective_error(comm, local_error, "adaptive Schwarz factor metadata")
    except RuntimeError:
        _destroy_class_factors(local_factor)
        raise

    patches = tuple(
        _Patch(
            patch_id=patch_id,
            cell_index=int(patch_id[1]),
            rows=rows,
            class_key=class_key,
            owner_rank=class_owner[class_key],
            weights=weights,
        )
        for patch_id, rows, class_key, weights in zip(
            patch_ids, patch_rows, class_keys, patch_weights, strict=True
        )
    )
    rows_min, rows_median, rows_max, row_count_histogram = _row_count_statistics(
        tuple(patch_rows), comm
    )
    patch_count = int(comm.allreduce(len(patches), MPI.SUM))
    class_reuse_saved_count = max(0, patch_count - len(unique_classes))
    factor_bytes = int(
        comm.allreduce(
            sum(item.factor_bytes for item in local_factor.values()), MPI.SUM
        )
    )
    factor_nnz = int(
        comm.allreduce(
            sum(item.factor_nnz for item in local_factor.values()), MPI.SUM
        )
    )
    bare_hash_after = _petsc_matrix_hash(bare_f)
    hash_matches = all(
        bool(value)
        for value in comm.allgather(bare_hash_before == bare_hash_after)
    )
    if not hash_matches:
        _destroy_class_factors(local_factor)
        raise RuntimeError("bare-F hash changed during adaptive Schwarz setup")
    actual_verified = bool(
        actual_provider is not None
        and isinstance(provider_audit, Mapping)
        and provider_audit.get("status") == "verified_exact_provider"
        and provider_audit.get("actual_hcurl_facet_form_assembler") is True
        and provider_audit.get("numeric_cache_released") is True
        and provider_audit.get("raw_cache_size_local") == 0
        and provider_audit.get("oriented_numeric_cache_size_local") == 0
    )
    diagnostics = {
        "schema": "task040.v8.adaptive_impedance_schwarz.component.v1",
        "overlap_semantics": "one_shared_entity_support",
        "patch_count": patch_count,
        "class_count": len(unique_classes),
        "class_reuse_saved_count": class_reuse_saved_count,
        "class_owner_by_key": dict(class_owner),
        "rows_min": rows_min,
        "rows_median": rows_median,
        "rows_max": rows_max,
        "row_count_histogram": row_count_histogram,
        "max_local_active_rows_cap": MAX_LOCAL_ACTIVE_ROWS,
        "owner_loads": comm.allgather(len(local_factor)),
        "factor_bytes_global": factor_bytes,
        "factor_nnz_global": factor_nnz,
        "factor_only_storage": True,
        "factor_class_reuse_enabled": True,
        "factor_class_reuse_observed": class_reuse_saved_count > 0,
        "pou_error": pou_error,
        "covered_active_rows": covered_rows,
        "active_rows": active_rows,
        "mass_audits_local": mass_audits_local,
        "raw_mass_audit_cache_size_local": len(mass_audits_local),
        "factor_probe_residual_ratio_by_class": dict(probe_by_class),
        "last_real_apply_patch_residual_ratio_source": "available_after_real_apply",
        "tangential_mass_source": (
            "actual_hcurl_ufcx_exterior_facet_provider"
            if actual_verified
            else "caller_declared_real_hcurl_tangential_trace_mass"
        ),
        "actual_hcurl_facet_form_assembler": actual_verified,
        "actual_hcurl_facet_form_assembler_status": (
            "verified_exact_provider" if actual_verified else "not_available"
        ),
        "exact_provider_audit": provider_audit,
        "numeric_collective_type": "bounded_object_alltoall",
        "numeric_object_alltoall_count_per_apply": 5,
        "metadata_collective_types": ["allgather", "alltoall", "allreduce"],
        "factor_probe_metadata_collective": "allgather",
        "max_sender_payload_bytes": 0,
        "max_owner_payload_bytes": 0,
        "global_sequential_union": False,
        "full_vector_numeric_allgather": False,
        "global_auxiliary_matrix": False,
        "outer_bare_f_unchanged": hash_matches,
        "bare_f_hash_before": bare_hash_before,
        "bare_f_hash_after": bare_hash_after,
        "setup_wall_seconds": float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        ),
        "cleanup": "action_releases_diagnostic_matrices_and_destroys_owned_factors;caller_destroys_borrowed_bare_f",
    }
    plan = AdaptiveImpedanceSchwarzPlan(
        patches=patches,
        row_ranges=ranges,
        diagnostics=diagnostics,
    )
    return AdaptiveImpedanceSchwarzAction(bare_f, plan, local_factor)
