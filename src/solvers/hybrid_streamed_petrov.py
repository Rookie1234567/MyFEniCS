"""Streamed owner-row basis construction for the V7 Lane B candidate."""

from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


V7_STREAMED_PETROV_CHECKPOINTS = (64, 128, 256, 512)
V7_STREAMED_PETROV_BATCH_SIZE = 1
V7_STREAMED_PETROV_PACKET_SCHEMA = "task039.v7.streamed_owner_row_basis.v2"
V7_STREAMED_PETROV_HASH_LAYOUT = "column-major-complex128-chunked-v1"
_V7_GRAM_ROW_BLOCK = 4096

__all__ = (
    "V7_STREAMED_PETROV_BATCH_SIZE",
    "V7_STREAMED_PETROV_CHECKPOINTS",
    "V7_STREAMED_PETROV_HASH_LAYOUT",
    "V7_STREAMED_PETROV_PACKET_SCHEMA",
    "StreamedOwnerRowBasisBuilder",
    "StreamedOwnerRowBasisPacket",
    "load_streamed_owner_row_basis_packet",
    "run_streamed_owner_row_basis_producer",
    "run_streamed_owner_row_petrov_consumer",
    "write_streamed_owner_row_basis_packet",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_sha256(array: np.ndarray, *, chunk_bytes: int = 1 << 20) -> str:
    """Hash a 1D/2D complex array in bounded column-major chunks."""

    values = np.asarray(array, dtype=np.complex128)
    if values.ndim not in (1, 2):
        raise ValueError("Streamed basis hash expects a one- or two-dimensional array")
    elements = max(int(chunk_bytes) // values.dtype.itemsize, 1)
    digest = hashlib.sha256()
    if values.ndim == 1:
        for start in range(0, values.size, elements):
            digest.update(
                np.ascontiguousarray(values[start : start + elements]).tobytes()
            )
        return digest.hexdigest()
    for column in range(values.shape[1]):
        column_values = values[:, column]
        for start in range(0, column_values.size, elements):
            digest.update(
                np.ascontiguousarray(column_values[start : start + elements]).tobytes()
            )
    return digest.hexdigest()


def _global_norm(values: np.ndarray, comm: MPI.Intracomm) -> float:
    local = float(np.vdot(values, values).real)
    return float(np.sqrt(max(comm.allreduce(local, op=MPI.SUM), 0.0)))


def _blocked_adjoint_matvec(
    matrix: np.ndarray, vector: np.ndarray, count: int
) -> np.ndarray:
    """Compute a local ``matrix[:,:count]^H @ vector`` with bounded temporaries."""

    result = np.zeros(int(count), dtype=np.complex128)
    for start in range(0, matrix.shape[0], _V7_GRAM_ROW_BLOCK):
        stop = min(start + _V7_GRAM_ROW_BLOCK, matrix.shape[0])
        block = matrix[start:stop, :count]
        result += np.conjugate(block).T @ vector[start:stop]
    return result


def _blocked_gram(left: np.ndarray, right: np.ndarray, count: int) -> np.ndarray:
    """Accumulate a bounded-row local Gram/cross matrix."""

    result = np.zeros((int(count), int(count)), dtype=np.complex128)
    for start in range(0, left.shape[0], _V7_GRAM_ROW_BLOCK):
        stop = min(start + _V7_GRAM_ROW_BLOCK, left.shape[0])
        left_block = left[start:stop, :count]
        right_block = right[start:stop, :count]
        result += np.conjugate(left_block).T @ right_block
    return result


def _compact_factor_inventory(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: values[key]
        for key in (
            "base_factor_count",
            "exact_factor_count",
            "global_direct_factor_count",
        )
        if key in values
    }


def _append_orthonormal_column(
    basis: np.ndarray,
    values: np.ndarray,
    *,
    column: int,
    comm: MPI.Intracomm,
    tolerance: float,
) -> None:
    """Two-pass MGS into a preallocated basis column."""

    work = np.array(values, dtype=np.complex128, copy=True, order="C")
    if column:
        prefix = basis[:, :column]
        for _ in range(2):
            local_coefficients = _blocked_adjoint_matvec(prefix, work, column)
            coefficients = np.empty_like(local_coefficients)
            comm.Allreduce(local_coefficients, coefficients, op=MPI.SUM)
            work -= prefix @ coefficients
    norm = _global_norm(work, comm)
    if not np.isfinite(norm) or norm <= tolerance:
        raise ValueError("Streamed owner-row source is rank deficient")
    basis[:, column] = work / norm


def _orthogonality_error(basis: np.ndarray, count: int, comm: MPI.Intracomm) -> float:
    local = _blocked_gram(basis, basis, count)
    global_gram = np.empty_like(local)
    comm.Allreduce(local, global_gram, op=MPI.SUM)
    return float(np.linalg.norm(global_gram - np.eye(count, dtype=np.complex128)))


class StreamedOwnerRowBasisBuilder:
    """Build nested Z/Y prefixes while retaining no source-column list."""

    capacity = max(V7_STREAMED_PETROV_CHECKPOINTS)

    def __init__(
        self,
        local_rows: int,
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        comm: MPI.Intracomm = MPI.COMM_WORLD,
        tolerance: float = 1.0e-13,
    ) -> None:
        first, last = (int(value) for value in ownership_range)
        if local_rows != last - first or first < 0 or last > int(global_rows):
            raise ValueError("Streamed owner-row ownership does not match local rows")
        if last <= first or int(global_rows) <= 0:
            raise ValueError("Streamed owner-row ownership is empty or invalid")
        if not np.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("Streamed owner-row tolerance must be positive and finite")
        self.comm = comm
        self.global_rows = int(global_rows)
        self.ownership_range = (first, last)
        self.tolerance = float(tolerance)
        self._z = np.empty((local_rows, self.capacity), dtype=np.complex128, order="F")
        self._y = np.empty((local_rows, self.capacity), dtype=np.complex128, order="F")
        self._source_digest = hashlib.sha256()
        self._right_digest = hashlib.sha256()
        self._left_digest = hashlib.sha256()
        self._source_count = 0
        self._right_bytes = 0
        self._left_bytes = 0
        self._prefix_records: list[dict[str, Any]] = []
        self._latest_checkpoint_diagnostics: dict[str, Any] | None = None
        self._destroyed = False

    @property
    def count(self) -> int:
        return int(self._source_count)

    @property
    def capacity_bytes(self) -> dict[str, int]:
        return {
            "z": int(self._z.nbytes),
            "y": int(self._y.nbytes),
            "total": int(self._z.nbytes + self._y.nbytes),
        }

    def append(
        self,
        right_local: np.ndarray,
        left_local: np.ndarray,
        *,
        source_identity: Mapping[str, Any],
    ) -> None:
        if self._destroyed:
            raise RuntimeError("Streamed owner-row basis builder is destroyed")
        if self._source_count >= self.capacity:
            raise ValueError("Streamed owner-row basis capacity is 512")
        right = np.asarray(right_local, dtype=np.complex128)
        left = np.asarray(left_local, dtype=np.complex128)
        expected_shape = (self._z.shape[0],)
        if right.shape != expected_shape or left.shape != expected_shape:
            raise ValueError("Streamed source does not match local owner rows")
        if not np.isfinite(right).all() or not np.isfinite(left).all():
            raise ValueError("Streamed source contains non-finite values")
        self._source_digest.update(_canonical_bytes(dict(source_identity)))
        self._right_digest.update(right.tobytes(order="C"))
        self._left_digest.update(left.tobytes(order="C"))
        self._right_bytes += int(right.nbytes)
        self._left_bytes += int(left.nbytes)
        column = self._source_count
        _append_orthonormal_column(
            self._z, right, column=column, comm=self.comm, tolerance=self.tolerance
        )
        _append_orthonormal_column(
            self._y, left, column=column, comm=self.comm, tolerance=self.tolerance
        )
        self._source_count += 1

    def _cross_diagnostics(self) -> tuple[float, float, float]:
        count = self._source_count
        if count == 0:
            return np.inf, np.nan, np.nan
        local_cross = _blocked_gram(self._y, self._z, count)
        cross = np.empty_like(local_cross)
        self.comm.Allreduce(local_cross, cross, op=MPI.SUM)
        singular_values = np.linalg.svd(cross, compute_uv=False)
        minimum = float(singular_values[-1])
        maximum = float(singular_values[0])
        condition = float(np.inf if minimum == 0.0 else maximum / minimum)
        return condition, minimum, maximum

    def _rank_hashes(self) -> list[dict[str, Any]]:
        return self.comm.allgather(
            {
                "rank": int(self.comm.rank),
                "ownership_range": list(self.ownership_range),
                "right_source_sha256": self._right_digest.hexdigest(),
                "left_source_sha256": self._left_digest.hexdigest(),
                "source_identity_sha256": self._source_digest.hexdigest(),
            }
        )

    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            raise RuntimeError("Streamed owner-row basis builder is destroyed")
        count = self._source_count
        condition, minimum, maximum = self._cross_diagnostics()
        return {
            "checkpoint": int(count),
            "rank": int(count),
            "local_rows": int(self._z.shape[0]),
            "global_rows": self.global_rows,
            "ownership_range": list(self.ownership_range),
            "owner_row_local": True,
            "global_basis_materialized": False,
            "source_columns_retained": False,
            "batch_size": V7_STREAMED_PETROV_BATCH_SIZE,
            "capacity_columns": self.capacity,
            "capacity_bytes": self.capacity_bytes,
            "current_prefix_bytes": {
                "z": int(self._z[:, :count].nbytes),
                "y": int(self._y[:, :count].nbytes),
            },
            "right_source_bytes": int(self._right_bytes),
            "left_source_bytes": int(self._left_bytes),
            "right_source_sha256": self._right_digest.hexdigest(),
            "left_source_sha256": self._left_digest.hexdigest(),
            "source_identity_sha256": self._source_digest.hexdigest(),
            "rank_hashes": self._rank_hashes(),
            "cross_yh_z_condition": condition,
            "cross_yh_z_singular_min": minimum,
            "cross_yh_z_singular_max": maximum,
            "z_orthogonality_error": _orthogonality_error(self._z, count, self.comm)
            if count
            else np.nan,
            "y_orthogonality_error": _orthogonality_error(self._y, count, self.comm)
            if count
            else np.nan,
            "basis_finite": bool(
                np.isfinite(self._z[:, :count]).all()
                and np.isfinite(self._y[:, :count]).all()
            ),
            "prefix_records": [dict(item) for item in self._prefix_records],
        }

    def checkpoint(
        self, checkpoint: int
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        if self._destroyed:
            raise RuntimeError("Streamed owner-row basis builder is destroyed")
        if checkpoint not in V7_STREAMED_PETROV_CHECKPOINTS:
            raise ValueError("Checkpoint is not in the frozen Lane B sequence")
        if int(checkpoint) != self._source_count:
            raise ValueError("Checkpoint must seal the current nested prefix")
        if (
            self._prefix_records
            and self._prefix_records[-1]["checkpoint"] == checkpoint
        ):
            raise ValueError("Checkpoint was already sealed")
        z_prefix = self._z[:, :checkpoint]
        y_prefix = self._y[:, :checkpoint]
        diagnostics = self.diagnostics()
        record = {
            "checkpoint": int(checkpoint),
            "hash_layout": V7_STREAMED_PETROV_HASH_LAYOUT,
            "z_prefix_sha256": _array_sha256(z_prefix),
            "y_prefix_sha256": _array_sha256(y_prefix),
            "source_identity_sha256": self._source_digest.hexdigest(),
            "right_source_sha256": self._right_digest.hexdigest(),
            "left_source_sha256": self._left_digest.hexdigest(),
            "z_orthogonality_error": diagnostics["z_orthogonality_error"],
            "y_orthogonality_error": diagnostics["y_orthogonality_error"],
            "cross_yh_z_condition": diagnostics["cross_yh_z_condition"],
        }
        self._prefix_records.append(record)
        diagnostics["prefix_records"] = [dict(item) for item in self._prefix_records]
        self._latest_checkpoint_diagnostics = diagnostics
        return z_prefix, y_prefix, diagnostics

    @property
    def latest_checkpoint_diagnostics(self) -> dict[str, Any] | None:
        if self._latest_checkpoint_diagnostics is None:
            return None
        return dict(self._latest_checkpoint_diagnostics)

    def final_basis(self) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
        if self._source_count != self.capacity:
            raise ValueError("Final streamed basis requires the 512-column prefix")
        if [item["checkpoint"] for item in self._prefix_records] != list(
            V7_STREAMED_PETROV_CHECKPOINTS
        ):
            raise ValueError("Final streamed basis lacks all nested prefix seals")
        return (
            self._z[:, : self._source_count],
            self._y[:, : self._source_count],
            [dict(item) for item in self._prefix_records],
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._z = np.empty((0, 0), dtype=np.complex128)
        self._y = np.empty((0, 0), dtype=np.complex128)
        self._prefix_records.clear()
        self._latest_checkpoint_diagnostics = None
        self._destroyed = True


class StreamedOwnerRowBasisPacket:
    """One mmap-backed rank-local final basis with explicit release."""

    def __init__(
        self,
        z: np.ndarray,
        y: np.ndarray,
        manifest: Mapping[str, Any],
        manifest_path: Path,
        shard: Mapping[str, Any],
    ) -> None:
        self.z = z
        self.y = y
        self.manifest = dict(manifest)
        self.manifest_path = manifest_path
        self.shard = dict(shard)
        self._destroyed = False

    def prefix(self, checkpoint: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        if self._destroyed or self.z is None or self.y is None:
            raise RuntimeError("Streamed basis packet is released")
        if checkpoint not in V7_STREAMED_PETROV_CHECKPOINTS:
            raise ValueError("Basis packet prefix is not frozen")
        record = next(
            item for item in self.shard["prefixes"] if item["checkpoint"] == checkpoint
        )
        if record.get("hash_layout") != V7_STREAMED_PETROV_HASH_LAYOUT:
            raise ValueError("Streamed basis prefix hash layout mismatch")
        z_prefix = self.z[:, :checkpoint]
        y_prefix = self.y[:, :checkpoint]
        if _array_sha256(z_prefix) != record["z_prefix_sha256"]:
            raise ValueError("Streamed basis Z prefix hash mismatch")
        if _array_sha256(y_prefix) != record["y_prefix_sha256"]:
            raise ValueError("Streamed basis Y prefix hash mismatch")
        return z_prefix, y_prefix, dict(record)

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            return {"mmap_retained": False, "mmap_released": True}
        return {
            "mmap_retained": True,
            "mmap_released": False,
            "arrays_retained": True,
            "owned_basis_copy_count": 0,
            "mmap_mapping_count": 2,
            "checkpoint": int(self.manifest["checkpoint"]),
            "hash_layout": V7_STREAMED_PETROV_HASH_LAYOUT,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.z = None
        self.y = None
        self._destroyed = True
        gc.collect()


def run_streamed_owner_row_basis_producer(
    packet_context: Any,
    schedule: Sequence[Mapping[str, Any]],
    source_builder: Callable[
        [Mapping[str, Any], Any], tuple[np.ndarray, np.ndarray, Mapping[str, Any]]
    ],
    *,
    output_directory: str | Path,
    global_rows: int,
    ownership_range: tuple[int, int],
    schedule_sha256: str,
    provenance: Mapping[str, Any],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Build one nested owner-row packet from one transient source pair at a time."""

    if len(schedule) != max(V7_STREAMED_PETROV_CHECKPOINTS):
        raise ValueError("Streamed producer requires the frozen 512-source schedule")
    if any(bool(item.get("holdout", False)) for item in schedule):
        raise ValueError("Streamed producer schedule cannot contain holdout sources")
    left_dual_oracle = provenance.get("left_dual_oracle")
    if not isinstance(left_dual_oracle, Mapping):
        raise ValueError("Streamed producer provenance needs a left-dual oracle")
    for branch in ("positive", "negative"):
        branch_oracle = left_dual_oracle.get(branch)
        if not isinstance(branch_oracle, Mapping) or not {
            "relative_error",
            "finite",
            "equivalent",
            "tolerance",
        }.issubset(branch_oracle):
            raise ValueError(
                f"Streamed producer {branch} left-dual oracle is incomplete"
            )
        error = float(branch_oracle["relative_error"])
        tolerance = float(branch_oracle["tolerance"])
        finite = bool(branch_oracle["finite"])
        equivalent = bool(branch_oracle["equivalent"])
        if (
            not np.isfinite(error)
            or not np.isfinite(tolerance)
            or tolerance <= 0.0
            or finite != bool(np.isfinite(error))
            or equivalent != bool(finite and error <= tolerance)
        ):
            raise ValueError(
                f"Streamed producer {branch} left-dual oracle is inconsistent"
            )
    if not all(
        bool(left_dual_oracle[branch]["equivalent"])
        for branch in ("positive", "negative")
    ):
        identity = provenance.get("source_schedule_identity")
        if not identity or str(identity) == "v6_full_owner_p_h_e":
            raise ValueError(
                "Non-equivalent streamed left dual needs a distinct source schedule"
            )
    first, last = (int(value) for value in ownership_range)
    builder = StreamedOwnerRowBasisBuilder(
        last - first,
        global_rows=int(global_rows),
        ownership_range=(first, last),
        comm=comm,
    )
    result: dict[str, Any] | None = None
    try:
        for item in schedule:
            right, left, source_identity = source_builder(item, packet_context)
            try:
                builder.append(right, left, source_identity=source_identity)
            finally:
                del right, left, source_identity
            if builder.count in V7_STREAMED_PETROV_CHECKPOINTS:
                builder.checkpoint(builder.count)
        z_local, y_local, prefix_records = builder.final_basis()
        result = write_streamed_owner_row_basis_packet(
            output_directory,
            z_local,
            y_local,
            prefix_records=prefix_records,
            global_rows=int(global_rows),
            ownership_range=(first, last),
            schedule_sha256=str(schedule_sha256),
            provenance=provenance,
            comm=comm,
        )
        producer_diagnostics = builder.latest_checkpoint_diagnostics
        if producer_diagnostics is None:
            raise RuntimeError("Streamed producer did not retain the final checkpoint")
        result["producer_diagnostics"] = producer_diagnostics
        return result
    finally:
        builder.destroy()
        packet_context_before_release = packet_context.diagnostics
        packet_context.release()
        if result is not None:
            result["packet_context_before_release"] = packet_context_before_release
            result["packet_context_after_release"] = packet_context.diagnostics


def run_streamed_owner_row_petrov_consumer(
    packet: Any,
    f_operator: PETSc.Mat,
    base_action: Any,
    *,
    holdout_evaluator: Callable[[Any, int], Mapping[str, Any]],
    checkpoint_callback: Callable[[str, int, Mapping[str, Any]], None] | None = None,
    factor_inventory: Mapping[str, Any] | None = None,
    condition_limit: float = 1.0e12,
) -> dict[str, Any]:
    """Evaluate one mmap basis packet through the frozen rank ladder."""

    from .hybrid_petrov_galerkin import (
        FixedLinearOwnerRowPetrovCorrectionAction,
        PetrovCoarseNumericalFailure,
    )

    comm = f_operator.getComm().tompi4py()

    base_diagnostics = getattr(base_action, "diagnostics", {})
    if callable(base_diagnostics):
        base_diagnostics = base_diagnostics()
    nested_ksp_count = base_diagnostics.get("nested_ksp_count")
    if nested_ksp_count is None or int(nested_ksp_count) != 0:
        raise ValueError("Streamed consumer requires nested_ksp_count=0")
    verified_factor_inventory = _compact_factor_inventory(base_diagnostics)
    if factor_inventory is not None:
        verified_factor_inventory.update(_compact_factor_inventory(factor_inventory))
    reports: list[dict[str, Any]] = []
    first_passing_checkpoint: int | None = None
    for checkpoint in V7_STREAMED_PETROV_CHECKPOINTS:
        z_local, y_local, prefix_record = packet.prefix(checkpoint)
        if checkpoint_callback is not None:
            checkpoint_callback(
                "setup_begin",
                int(checkpoint),
                {"prefix_record": dict(prefix_record)},
            )
        setup_started = perf_counter()
        try:
            action = FixedLinearOwnerRowPetrovCorrectionAction(
                base_action,
                f_operator,
                z_local,
                y_local,
                factor_inventory=factor_inventory,
                condition_limit=condition_limit,
                basis_ownership="borrowed_readonly",
            )
        except PetrovCoarseNumericalFailure as error:
            setup_seconds = float(
                comm.allreduce(perf_counter() - setup_started, op=MPI.MAX)
            )
            reports.append(
                {
                    "checkpoint": int(checkpoint),
                    "prefix_record": dict(prefix_record),
                    "basis_mmap_borrowed": True,
                    "action_owned_prefix_copy": False,
                    "status": "numerical_e_failure",
                    "gate_pass": False,
                    "implementation_failure": False,
                    "e_failure": str(error),
                    "e_gate": dict(error.diagnostics),
                    "correction_action_destroyed": True,
                    "petrov_diagnostics": None,
                    "post_destroy_diagnostics": None,
                    "factor_inventory": dict(verified_factor_inventory),
                    "factor_inventory_source": "verified_base_or_explicit",
                    "setup_seconds": setup_seconds,
                    "holdout_seconds": 0.0,
                    "correction_apply_seconds": 0.0,
                    "correction_apply_timing_status": "not_run_e_failure",
                    "timing_status": "holdout_not_run_after_e_failure",
                }
            )
            if checkpoint_callback is not None:
                checkpoint_callback(
                    "setup_end",
                    int(checkpoint),
                    {
                        "status": "numerical_e_failure",
                        "setup_seconds": setup_seconds,
                        "e_gate": dict(error.diagnostics),
                    },
                )
            del z_local, y_local
            continue
        setup_seconds = float(
            comm.allreduce(perf_counter() - setup_started, op=MPI.MAX)
        )
        report: dict[str, Any] = {
            "checkpoint": int(checkpoint),
            "prefix_record": dict(prefix_record),
            "basis_mmap_borrowed": True,
            "action_owned_prefix_copy": False,
            "petrov_diagnostics": action.diagnostics,
            "status": "pending",
            "e_failure": None,
            "implementation_failure": False,
            "post_destroy_diagnostics": None,
            "factor_inventory": dict(verified_factor_inventory),
            "factor_inventory_source": "verified_base_or_explicit",
            "setup_seconds": setup_seconds,
            "holdout_seconds": None,
            "correction_apply_seconds": None,
            "correction_apply_timing_status": "pending",
            "timing_status": "pending",
        }
        if checkpoint_callback is not None:
            checkpoint_callback(
                "setup_end",
                int(checkpoint),
                {
                    "status": "ready",
                    "setup_seconds": setup_seconds,
                    "petrov_diagnostics": action.diagnostics,
                },
            )
        del z_local, y_local
        try:
            holdout_started = perf_counter()
            evaluated = dict(holdout_evaluator(action, int(checkpoint)))
            holdout_seconds = float(
                comm.allreduce(perf_counter() - holdout_started, op=MPI.MAX)
            )
            if "gate_pass" not in evaluated:
                raise ValueError("Streamed holdout evaluator must return gate_pass")
            report.update(evaluated)
            report["holdout_seconds"] = evaluated.get(
                "holdout_seconds", holdout_seconds
            )
            action_diagnostics = action.diagnostics
            local_apply_timing = np.asarray(
                [
                    float(action_diagnostics["total_apply_seconds"]),
                    float(action_diagnostics["last_apply_seconds"]),
                ],
                dtype=np.float64,
            )
            apply_timing = np.empty_like(local_apply_timing)
            comm.Allreduce(local_apply_timing, apply_timing, op=MPI.MAX)
            report["correction_apply_seconds"] = float(apply_timing[0])
            report["correction_last_apply_seconds"] = float(apply_timing[1])
            report["correction_apply_timing_status"] = "measured_mpi_max"
            report["timing_status"] = "measured_mpi_max"
            report["status"] = (
                "completed" if bool(report["gate_pass"]) else "numerical_gate_failed"
            )
            if checkpoint_callback is not None:
                checkpoint_callback(
                    "holdout_end",
                    int(checkpoint),
                    {
                        "holdout_seconds": report["holdout_seconds"],
                        "correction_apply_seconds": report["correction_apply_seconds"],
                        "correction_last_apply_seconds": report[
                            "correction_last_apply_seconds"
                        ],
                        "gate": report.get("gate"),
                        "gate_pass": bool(report["gate_pass"]),
                    },
                )
        finally:
            action.destroy()
            report["post_destroy_diagnostics"] = action.diagnostics
            report["factor_inventory"] = _compact_factor_inventory(
                report["post_destroy_diagnostics"]
            )
            report["correction_action_destroyed"] = bool(
                report["post_destroy_diagnostics"].get("destroyed", False)
            )
        reports.append(report)
        if bool(report["gate_pass"]):
            first_passing_checkpoint = int(checkpoint)
            break
    completed_reports = [
        report
        for report in reports
        if report.get("post_destroy_diagnostics") is not None
    ]
    final_diagnostics = (
        completed_reports[-1]["post_destroy_diagnostics"] if completed_reports else {}
    )
    final_inventory = _compact_factor_inventory(
        final_diagnostics
        or (reports[-1].get("factor_inventory", {}) if reports else {})
        or verified_factor_inventory
    )
    factor_inventory_verified = bool(
        final_inventory.get("exact_factor_count") == 0
        and final_inventory.get("global_direct_factor_count") == 0
    )
    return {
        "reports": reports,
        "first_passing_checkpoint": first_passing_checkpoint,
        "nested_ksp_count": int(nested_ksp_count),
        "factor_inventory": final_inventory,
        "exact_factor_count": final_inventory.get("exact_factor_count"),
        "global_direct_factor_count": final_inventory.get("global_direct_factor_count"),
        "all_corrections_destroyed": all(
            bool(report.get("correction_action_destroyed", False)) for report in reports
        ),
        "factor_inventory_verified": factor_inventory_verified,
        "packet_release_required_by_caller": True,
    }


def write_streamed_owner_row_basis_packet(
    directory: str | Path,
    z_local: np.ndarray,
    y_local: np.ndarray,
    *,
    prefix_records: list[Mapping[str, Any]],
    global_rows: int,
    ownership_range: tuple[int, int],
    schedule_sha256: str,
    provenance: Mapping[str, Any],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Write one final 512-column packet containing all nested prefixes."""

    z = np.asarray(z_local, dtype=np.complex128)
    y = np.asarray(y_local, dtype=np.complex128)
    first, last = (int(value) for value in ownership_range)
    if z.shape != y.shape or z.ndim != 2 or z.shape[1] != 512:
        raise ValueError("Basis packet requires one final 512-column prefix")
    if z.shape[0] != last - first:
        raise ValueError("Basis packet ownership does not match local rows")
    if [item["checkpoint"] for item in prefix_records] != list(
        V7_STREAMED_PETROV_CHECKPOINTS
    ):
        raise ValueError("Basis packet requires all nested prefix records")
    if not provenance.get("training_holdout_disjoint", False):
        raise ValueError("Basis packet must prove training/holdout separation")
    path = Path(directory)
    if comm.rank == 0:
        path.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    z_path = path / f"rank{comm.rank:04d}_z.npy"
    y_path = path / f"rank{comm.rank:04d}_y.npy"
    np.save(z_path, z, allow_pickle=False)
    np.save(y_path, y, allow_pickle=False)
    prefixes = []
    for item in prefix_records:
        prefix = dict(item)
        prefix["schedule_sha256"] = str(schedule_sha256)
        prefix["hash_layout"] = V7_STREAMED_PETROV_HASH_LAYOUT
        prefixes.append(prefix)
    shard = {
        "rank": int(comm.rank),
        "ownership_range": [first, last],
        "prefixes": prefixes,
        "z": {
            "path": z_path.name,
            "sha256": _sha256_file(z_path),
            "shape": list(z.shape),
            "dtype": "complex128",
        },
        "y": {
            "path": y_path.name,
            "sha256": _sha256_file(y_path),
            "shape": list(y.shape),
            "dtype": "complex128",
        },
    }
    shards = sorted(comm.allgather(shard), key=lambda item: item["ownership_range"][0])
    expected = 0
    for item in shards:
        start, end = (int(value) for value in item["ownership_range"])
        if start != expected:
            raise ValueError("Basis packet ownership has a gap or overlap")
        expected = end
    if expected != int(global_rows):
        raise ValueError("Basis packet ownership does not cover global rows")
    manifest = {
        "schema": V7_STREAMED_PETROV_PACKET_SCHEMA,
        "hash_layout": V7_STREAMED_PETROV_HASH_LAYOUT,
        "checkpoint": 512,
        "prefix_checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
        "global_rows": int(global_rows),
        "rank_count": int(comm.size),
        "schedule_sha256": str(schedule_sha256),
        "provenance": dict(provenance),
        "shards": shards,
    }
    manifest_path = path / "manifest.json"
    if comm.rank == 0:
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        )
    comm.barrier()
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "checkpoint": 512,
        "prefix_checkpoints": list(V7_STREAMED_PETROV_CHECKPOINTS),
        "hash_layout": V7_STREAMED_PETROV_HASH_LAYOUT,
        "rank_hashes": shards,
        "writer_retained_basis_copy": False,
    }


def load_streamed_owner_row_basis_packet(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_schedule_sha256: str,
    expected_provenance: Mapping[str, Any],
    ownership_range: tuple[int, int],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> StreamedOwnerRowBasisPacket:
    """Load mmap-backed owner rows; current prefixes are verified on demand."""

    path = Path(manifest_path)
    manifest_sha256 = _sha256_file(path)
    if manifest_sha256 != str(expected_manifest_sha256):
        raise ValueError("Streamed basis manifest hash mismatch before read")
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != V7_STREAMED_PETROV_PACKET_SCHEMA:
        raise ValueError("Streamed basis packet schema mismatch")
    if manifest.get("prefix_checkpoints") != list(V7_STREAMED_PETROV_CHECKPOINTS):
        raise ValueError("Streamed basis packet prefix contract mismatch")
    if manifest.get("schedule_sha256") != str(expected_schedule_sha256):
        raise ValueError("Streamed basis schedule hash mismatch")
    if manifest.get("hash_layout") != V7_STREAMED_PETROV_HASH_LAYOUT:
        raise ValueError("Streamed basis hash layout mismatch")
    if manifest.get("provenance") != dict(expected_provenance):
        raise ValueError("Streamed basis provenance mismatch")
    if int(manifest.get("rank_count", -1)) != int(comm.size):
        raise ValueError("Streamed basis rank count mismatch")
    first, last = (int(value) for value in ownership_range)
    shard = next(
        (item for item in manifest["shards"] if int(item["rank"]) == comm.rank),
        None,
    )
    if shard is None or tuple(shard["ownership_range"]) != (first, last):
        raise ValueError("Streamed basis target ownership mismatch")

    def read_array(role: str) -> np.ndarray:
        info = shard[role]
        if info.get("dtype") != "complex128":
            raise ValueError("Streamed basis dtype mismatch")
        array_path = path.parent / info["path"]
        if _sha256_file(array_path) != info["sha256"]:
            raise ValueError("Streamed basis shard hash mismatch")
        mapped = np.load(array_path, mmap_mode="r", allow_pickle=False)
        if list(mapped.shape) != list(info["shape"]):
            del mapped
            raise ValueError("Streamed basis shard shape mismatch")
        return mapped

    z = read_array("z")
    try:
        y = read_array("y")
    except Exception:
        del z
        raise
    if _sha256_file(path) != str(expected_manifest_sha256):
        del z, y
        raise ValueError("Streamed basis manifest changed during read")
    return StreamedOwnerRowBasisPacket(z, y, manifest, path, shard)
