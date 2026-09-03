"""Bounded-memory, disk-backed unrestarted right FGMRES.

This module is an oracle component, not a production preconditioner.  The
Arnoldi ``V`` and flexible ``Z`` columns live in two positional raw files;
only one column is read at a time.  The small Hessenberg problem remains in
memory, while the full-vector window is deliberately limited to eight
solver-owned arrays.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


MAX_STEPS = 500
CHECKPOINT_INTERVAL = 20
ORTHOGONALITY_LIMIT = 1.0e-8
EXPLICIT_ARNOLDI_LIMIT = 1.0e-8
FULL_VECTOR_BUFFER_LIMIT = 8
_COMPLEX128 = np.dtype(np.complex128)
_VECTOR_BYTES = _COMPLEX128.itemsize


def _finite_vector(values: Any, rows: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if (
        array.ndim != 1
        or array.shape[0] != rows
        or array.dtype != _COMPLEX128
        or not np.all(np.isfinite(array))
    ):
        raise TypeError(f"{name} must be a finite complex128 vector of length {rows}")
    return array


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(values)).cast("B")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _write_all(fd: int, data: memoryview, offset: int) -> None:
    moved = 0
    while moved < len(data):
        count = os.pwrite(fd, data[moved:], offset + moved)
        if count <= 0:
            raise OSError("short positional basis write")
        moved += count


def _read_all(fd: int, target: np.ndarray, offset: int) -> None:
    view = memoryview(target).cast("B")
    moved = 0
    while moved < len(view):
        block = os.pread(fd, len(view) - moved, offset + moved)
        if not block:
            raise OSError("short positional basis read")
        view[moved : moved + len(block)] = block
        moved += len(block)


class _PositionalColumns:
    """One exclusive raw file with fixed-size, in-order columns."""

    def __init__(self, path: Path, rows: int, capacity: int) -> None:
        self.path = Path(path)
        self.rows = int(rows)
        self.capacity = int(capacity)
        self.bytes_per_column = self.rows * _VECTOR_BYTES
        self.allocated_bytes = self.capacity * self.bytes_per_column
        self.fd = os.open(
            self.path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR,
            0o600,
        )
        try:
            os.ftruncate(self.fd, self.allocated_bytes)
        except Exception:
            os.close(self.fd)
            raise
        self.written = 0
        self.read_count = 0
        self.records: list[dict[str, Any]] = []
        self.sync_columns: list[int] = []

    def write(self, values: np.ndarray) -> dict[str, Any]:
        if self.written >= self.capacity:
            raise ValueError("basis capacity exceeded")
        values = _finite_vector(values, self.rows, "basis column")
        if not values.flags.c_contiguous:
            raise TypeError("basis columns must be C-contiguous")
        index = self.written
        payload = memoryview(values).cast("B")
        offset = index * self.bytes_per_column
        _write_all(self.fd, payload, offset)
        record = {
            "column": index,
            "offset": offset,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        self.records.append(record)
        self.written += 1
        return record

    def read(self, index: int, target: np.ndarray) -> None:
        if not 0 <= int(index) < self.written:
            raise IndexError("basis column is not available")
        target = np.asarray(target)
        if (
            target.ndim != 1
            or target.shape[0] != self.rows
            or target.dtype != _COMPLEX128
            or not target.flags.c_contiguous
        ):
            raise TypeError("basis read buffer must be C-contiguous")
        _read_all(self.fd, target, int(index) * self.bytes_per_column)
        self.read_count += 1

    def sync(self, column: int) -> None:
        os.fdatasync(self.fd)
        self.sync_columns.append(int(column))

    def close(self) -> None:
        try:
            os.fsync(self.fd)
        finally:
            os.close(self.fd)

    def facts(self) -> dict[str, Any]:
        return {
            "path": self.path.name,
            "rows": self.rows,
            "dtype": "complex128",
            "capacity": self.capacity,
            "written_count": self.written,
            "read_count": self.read_count,
            "allocated_bytes": self.allocated_bytes,
            "records": list(self.records),
            "sync_cadence": CHECKPOINT_INTERVAL,
            "sync_columns": list(self.sync_columns),
            "mmap": False,
        }


def _exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _apply_checked(
    function: Callable[[np.ndarray], Any], values: np.ndarray, rows: int, name: str
) -> np.ndarray:
    output = function(values)
    array = _finite_vector(output, rows, name)
    if np.shares_memory(array, values) or not array.flags.c_contiguous:
        raise TypeError(f"{name} callback must return an independent C-contiguous vector")
    return array


def run_disk_backed_right_fgmres(
    rhs: np.ndarray,
    action: Callable[[np.ndarray], np.ndarray],
    pc: Callable[[np.ndarray], np.ndarray],
    *,
    scratch_root: str | Path,
    max_steps: int = MAX_STEPS,
    initial_solution: np.ndarray | None = None,
    checkpoint_interval: int = CHECKPOINT_INTERVAL,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one unrestarted right-FGMRES oracle.

    ``max_steps`` is bounded by the V17 fixed cap of 500 and
    ``checkpoint_interval`` is fixed at 20.  The observer is synchronous and
    receives borrowed arrays; it must retain only scalar facts or copies.
    ``scratch_root`` is exclusive, so a second run cannot silently reuse a
    basis.
    """

    if not isinstance(max_steps, int) or not 1 <= max_steps <= MAX_STEPS:
        raise ValueError("V17 unrestarted FGMRES max_steps must be in [1, 500]")
    if checkpoint_interval != CHECKPOINT_INTERVAL:
        raise ValueError("V17 unrestarted FGMRES checkpoint cadence is fixed at 20")
    if observer is not None and not callable(observer):
        raise TypeError("observer must be callable or None")
    rhs_input = np.asarray(rhs)
    if rhs_input.ndim != 1 or rhs_input.dtype != _COMPLEX128:
        raise TypeError("rhs must be a complex128 vector")
    rows = int(rhs_input.size)
    rhs_values = _finite_vector(rhs_input, rows, "rhs")
    rhs_input_before = _array_sha256(rhs_input)
    if initial_solution is None:
        initial_values = np.zeros(rows, dtype=_COMPLEX128)
        initial_input = None
        initial_provided = False
    else:
        initial = np.asarray(initial_solution)
        if initial.ndim != 1 or initial.dtype != _COMPLEX128:
            raise TypeError("initial_solution must be a complex128 vector")
        initial_values = _finite_vector(initial, rows, "initial_solution")
        initial_input = initial
        initial_provided = True
    initial_input_before = (
        _array_sha256(initial_input) if initial_input is not None else None
    )
    scratch = Path(scratch_root)
    scratch.mkdir(parents=False, exist_ok=False)

    v_store: _PositionalColumns | None = None
    z_store: _PositionalColumns | None = None
    try:
        v_store = _PositionalColumns(scratch / "V.bin", rows, max_steps + 1)
        z_store = _PositionalColumns(scratch / "Z.bin", rows, max_steps)
        solution = np.array(initial_values, copy=True)
        residual = np.empty(rows, dtype=_COMPLEX128)
        v_current = np.empty(rows, dtype=_COMPLEX128)
        v_read = np.empty(rows, dtype=_COMPLEX128)
        work = np.empty(rows, dtype=_COMPLEX128)
        hessenberg = np.zeros((max_steps + 1, max_steps), dtype=_COMPLEX128)
        least_squares_rhs = np.zeros(max_steps + 1, dtype=_COMPLEX128)
        action_count = 0
        pc_count = 0
        explicit_action_count = 0
        history: list[dict[str, Any]] = []
        max_orthogonality = 0.0
        sync_columns: list[dict[str, Any]] = []
        happy_breakdown_records: list[dict[str, Any]] = []

        work[:] = _apply_checked(action, solution, rows, "initial action")
        action_count += 1
        residual[:] = rhs_values
        residual -= work
        rhs_norm = max(float(np.linalg.norm(rhs_values)), np.finfo(float).tiny)
        residual_norm = float(np.linalg.norm(residual))
        initial_true_relative = residual_norm / rhs_norm
        if residual_norm == 0.0:
            final_action = _apply_checked(action, solution, rows, "final action")
            action_count += 1
            residual[:] = rhs_values
            residual -= final_action
            final_norm = float(np.linalg.norm(residual))
            final_relative = float(np.linalg.norm(residual)) / rhs_norm
            final_action = None
            iterations = 0
            h_rows = 0
        else:
            least_squares_rhs[0] = residual_norm
            v_current[:] = residual / residual_norm
            v_store.write(v_current)
            iterations = 0
            for column in range(max_steps):
                iterations = column + 1
                work[:] = _apply_checked(pc, v_current, rows, "PC output")
                pc_count += 1
                z_store.write(work)
                residual[:] = _apply_checked(action, work, rows, "action output")
                action_count += 1
                operator_norm = float(np.linalg.norm(residual))
                for _ in range(2):
                    for previous in range(column + 1):
                        v_store.read(previous, v_read)
                        coefficient = np.vdot(v_read, residual)
                        hessenberg[previous, column] += coefficient
                        residual -= coefficient * v_read
                next_norm = float(np.linalg.norm(residual))
                hessenberg[column + 1, column] = next_norm
                happy_breakdown_threshold = (
                    64.0
                    * np.finfo(np.float64).eps
                    * max(1.0, operator_norm)
                )
                happy_breakdown = bool(next_norm <= happy_breakdown_threshold)
                happy_breakdown_records.append(
                    {
                        "iteration": iterations,
                        "operator_norm": operator_norm,
                        "next_norm": next_norm,
                        "threshold": happy_breakdown_threshold,
                        "triggered": happy_breakdown,
                    }
                )
                if happy_breakdown:
                    h_rows = column + 1
                else:
                    h_rows = column + 2
                    v_current[:] = residual / next_norm
                    v_store.write(v_current)
                    for previous in range(column + 1):
                        v_store.read(previous, v_read)
                        max_orthogonality = max(
                            max_orthogonality,
                            float(abs(np.vdot(v_read, v_current))),
                        )

                if iterations % CHECKPOINT_INTERVAL == 0 or iterations == max_steps:
                    matrix = hessenberg[:h_rows, :iterations]
                    coefficients = np.linalg.lstsq(
                        matrix,
                        least_squares_rhs[:h_rows],
                        rcond=None,
                    )[0]
                    solution[:] = initial_values
                    for basis_column in range(iterations):
                        z_store.read(basis_column, v_read)
                        solution += coefficients[basis_column] * v_read
                    estimated_norm = float(
                        np.linalg.norm(
                            least_squares_rhs[:h_rows] - matrix @ coefficients
                        )
                    )
                    work[:] = _apply_checked(action, solution, rows, "checkpoint action")
                    action_count += 1
                    explicit_action_count += 1
                    residual[:] = rhs_values
                    residual -= work
                    true_norm = float(np.linalg.norm(residual))
                    true_relative = true_norm / rhs_norm
                    closure = abs(true_norm - estimated_norm) / max(
                        rhs_norm, np.finfo(float).tiny
                    )
                    row = {
                        "iteration": iterations,
                        "true_residual_norm": true_norm,
                        "true_relative_residual": true_relative,
                        "arnoldi_residual_norm": estimated_norm,
                        "explicit_vs_arnoldi_relative": closure,
                        "finite": bool(
                            np.isfinite(true_norm)
                            and np.isfinite(estimated_norm)
                            and np.all(np.isfinite(solution))
                            and np.all(np.isfinite(residual))
                        ),
                    }
                    history.append(row)
                    if observer is not None:
                        observer(
                            {
                                **row,
                                "solution": solution,
                                "action": work,
                                "residual": residual,
                                "rhs": rhs_values,
                            }
                        )
                    if iterations % CHECKPOINT_INTERVAL == 0:
                        v_store.sync(iterations)
                        z_store.sync(iterations)
                        sync_columns.append({"iteration": iterations, "V": iterations, "Z": iterations})
                if happy_breakdown:
                    break

            if not history or int(history[-1]["iteration"]) != iterations:
                matrix = hessenberg[: h_rows, :iterations]
                coefficients = np.linalg.lstsq(
                    matrix,
                    least_squares_rhs[:h_rows],
                    rcond=None,
                )[0]
                solution[:] = initial_values
                for basis_column in range(iterations):
                    z_store.read(basis_column, v_read)
                    solution += coefficients[basis_column] * v_read
                work[:] = _apply_checked(action, solution, rows, "final action")
                action_count += 1
                residual[:] = rhs_values
                residual -= work
                final_norm = float(np.linalg.norm(residual))
                final_relative = final_norm / rhs_norm
            else:
                final_norm = float(history[-1]["true_residual_norm"])
                final_relative = float(history[-1]["true_relative_residual"])
        rhs_input_after = _array_sha256(rhs_input)
        initial_input_after = (
            _array_sha256(initial_input) if initial_input is not None else None
        )
        input_unchanged = (
            rhs_input_before == rhs_input_after
            and initial_input_before == initial_input_after
        )
        vector_bytes = rows * _VECTOR_BYTES
        buffer_names = (
            "rhs_borrowed",
            "initial_solution_borrowed" if initial_provided else "initial_solution_zero",
            "solution",
            "residual",
            "v_current",
            "v_read",
            "work",
        )
        callback_output_count = 1
        persistent_buffer_count = len(buffer_names)
        peak_buffer_count = persistent_buffer_count + callback_output_count
        lifecycle_names = [*buffer_names, "callback_output"]
        buffer_lifecycle = {
            phase: {"count": peak_buffer_count, "names": lifecycle_names}
            for phase in ("initial", "arnoldi", "checkpoint", "final")
        }
        hessenberg_values = np.array(hessenberg[:h_rows, :iterations], copy=True)
        hessenberg_path = scratch / "H.npy"
        with hessenberg_path.open("xb") as stream:
            np.save(stream, hessenberg_values, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        hessenberg_descriptor = {
            "path": hessenberg_path.name,
            "rows": int(hessenberg_values.shape[0]),
            "columns": int(hessenberg_values.shape[1]),
            "dtype": "complex128",
            "bytes": int(hessenberg_path.stat().st_size),
            "sha256": _file_sha256(hessenberg_path),
        }
        scratch_manifest = {
            "schema": "task038.v17.disk-fgmres.basis.v1",
            "algorithm": "right_flexible_gmres_unrestarted",
            "rows": rows,
            "dtype": "complex128",
            "max_steps": max_steps,
            "iterations": iterations,
            "mmap": False,
            "basis_in_memory": False,
            "H": hessenberg_descriptor,
            "V": v_store.facts(),
            "Z": z_store.facts(),
        }
        _exclusive_json(scratch / "basis_manifest.json", scratch_manifest)
        audit = {
            "algorithm": "right_flexible_gmres_unrestarted",
            "max_steps": max_steps,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "checkpoint_iterations": [int(row["iteration"]) for row in history],
            "initial_true_residual": initial_true_relative,
            "iterations": iterations,
            "action_count": action_count,
            "pc_count": pc_count,
            "explicit_action_count": explicit_action_count,
            "orthogonalization_passes": 2,
            "orthogonality_max_abs": float(max_orthogonality),
            "orthogonality_limit": ORTHOGONALITY_LIMIT,
            "explicit_arnoldi_limit": EXPLICIT_ARNOLDI_LIMIT,
            "hessenberg_finite": bool(np.all(np.isfinite(hessenberg[: h_rows, :iterations]))),
            "hessenberg_shape": [int(h_rows), int(iterations)],
            "hessenberg": hessenberg_descriptor,
            "happy_breakdown_formula": "64*eps*max(1,operator_norm)",
            "happy_breakdown_records": happy_breakdown_records,
            "persistent_full_vector_buffer_count": persistent_buffer_count,
            "callback_output_buffer_count": callback_output_count,
            "bounded_full_vector_buffer_count": peak_buffer_count,
            "bounded_full_vector_buffer_gate": peak_buffer_count <= FULL_VECTOR_BUFFER_LIMIT,
            "bounded_full_vector_bytes": peak_buffer_count * vector_bytes,
            "buffer_lifecycle": buffer_lifecycle,
            "scratch_bytes": int(v_store.allocated_bytes + z_store.allocated_bytes),
            "scratch_manifest": "basis_manifest.json",
            "sync_cadence": CHECKPOINT_INTERVAL,
            "sync_columns": sync_columns,
            "input_rhs_before_sha256": rhs_input_before,
            "input_rhs_after_sha256": rhs_input_after,
            "input_initial_before_sha256": initial_input_before,
            "input_initial_after_sha256": initial_input_after,
            "input_unchanged": input_unchanged,
            "initial_solution_provided": initial_provided,
            "final_solution_finite": bool(np.all(np.isfinite(solution))),
        }
        return {
            "solution": solution,
            "iterations": int(iterations),
            "final_true_residual_norm": float(final_norm),
            "final_relative_residual": float(final_relative),
            "history": history,
            "hessenberg": hessenberg_values,
            "audit": audit,
        }
    finally:
        if z_store is not None:
            z_store.close()
        if v_store is not None:
            v_store.close()


__all__ = (
    "CHECKPOINT_INTERVAL",
    "EXPLICIT_ARNOLDI_LIMIT",
    "FULL_VECTOR_BUFFER_LIMIT",
    "MAX_STEPS",
    "ORTHOGONALITY_LIMIT",
    "run_disk_backed_right_fgmres",
)
