"""A small disk-backed right flexible-GMRES cycle.

The Arnoldi vectors are stored in preallocated raw files and are transferred
with positional I/O.  Only the current full vectors and the small Hessenberg
problem are live in Python memory; checkpoint arrays are borrowed by the
optional observer and are not retained by the solver.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import numpy as np


__all__ = [
    "RawPositionalColumnStore",
    "DiskBackedFlexibleGMRES",
    "DiskBackedFlexibleGMRESResult",
]


_COMPLEX128 = np.dtype(np.complex128)
_COMPLEX128_BYTES = _COMPLEX128.itemsize
_FLOAT_EPS = np.finfo(np.float64).eps
_FULL_VECTOR_BUFFER_LIMIT_BYTES = 64 * 1024 * 1024
_BREAKDOWN_MULTIPLIER = 64.0


def _require_vector(values: Any, rows: int, name: str) -> np.ndarray:
    array = np.asarray(values)
    if (
        array.ndim != 1
        or array.shape[0] != rows
        or array.dtype != _COMPLEX128
        or not np.all(np.isfinite(array))
    ):
        raise TypeError(f"{name} must be a finite complex128 vector of length {rows}")
    return array


def _positional_transfer(
    file_descriptor: int,
    buffer: np.ndarray,
    offset: int,
    *,
    write: bool,
) -> None:
    """Transfer one contiguous ndarray through raw positional I/O."""

    contiguous = np.ascontiguousarray(buffer)
    view = memoryview(contiguous).cast("B")
    moved = 0
    while moved < len(view):
        if write:
            count = os.pwritev(file_descriptor, [view[moved:]], offset + moved)
        else:
            count = os.preadv(file_descriptor, [view[moved:]], offset + moved)
        if count <= 0:
            raise OSError("short positional basis-file transfer")
        moved += count
    if not write and contiguous is not buffer:
        buffer[...] = contiguous


class RawPositionalColumnStore:
    def __init__(self, path: Path, rows: int, capacity: int) -> None:
        self.path = path
        self.rows = rows
        self.capacity = capacity
        self._file_descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR,
            0o600,
        )
        self.allocated_bytes = rows * capacity * _COMPLEX128_BYTES
        os.ftruncate(self._file_descriptor, self.allocated_bytes)
        self.written_count = 0
        self.read_count = 0
        self.write_count = 0
        self.bytes_read = 0
        self.bytes_written = 0
        self._closed = False

    @classmethod
    def open_readonly(cls, path: Path, rows: int, capacity: int) -> "RawPositionalColumnStore":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        expected_bytes = rows * capacity * _COMPLEX128_BYTES
        if path.stat().st_size != expected_bytes:
            raise ValueError("raw positional column file size is invalid")
        result = object.__new__(cls)
        result.path = path
        result.rows = rows
        result.capacity = capacity
        result._file_descriptor = os.open(path, os.O_RDONLY)
        result.allocated_bytes = expected_bytes
        result.written_count = capacity
        result.read_count = 0
        result.write_count = 0
        result.bytes_read = 0
        result.bytes_written = 0
        result._closed = False
        return result

    def write_column(self, index: int, values: np.ndarray) -> None:
        if index != self.written_count or index >= self.capacity:
            raise ValueError("basis columns must be written once in order")
        values = _require_vector(values, self.rows, "basis column")
        if not values.flags.c_contiguous:
            raise TypeError("basis column must be C-contiguous")
        _positional_transfer(
            self._file_descriptor,
            values,
            index * self.rows * _COMPLEX128_BYTES,
            write=True,
        )
        self.written_count += 1
        self.write_count += 1
        self.bytes_written += self.rows * _COMPLEX128_BYTES

    def read_column(self, index: int, target: np.ndarray) -> None:
        if index < 0 or index >= self.written_count:
            raise IndexError("basis column has not been written")
        target = np.asarray(target)
        if (
            target.ndim != 1
            or target.shape[0] != self.rows
            or target.dtype != _COMPLEX128
            or not target.flags.c_contiguous
        ):
            raise TypeError("basis read buffer must be C-contiguous complex128")
        _positional_transfer(
            self._file_descriptor,
            target,
            index * self.rows * _COMPLEX128_BYTES,
            write=False,
        )
        self.read_count += 1
        self.bytes_read += self.rows * _COMPLEX128_BYTES

    def audit(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "rows": self.rows,
            "dtype": "complex128",
            "capacity": self.capacity,
            "written_count": self.written_count,
            "read_count": self.read_count,
            "write_count": self.write_count,
            "allocated_bytes": self.allocated_bytes,
            "bytes_read": self.bytes_read,
            "bytes_written": self.bytes_written,
            "mmap": False,
        }

    def close(self) -> None:
        if not self._closed:
            os.close(self._file_descriptor)
            self._closed = True


@dataclass(frozen=True)
class DiskBackedFlexibleGMRESResult:
    """Result retaining only the final solution and small cycle metadata."""

    solution: np.ndarray
    iterations: int
    happy_breakdown: bool
    checkpoints: Mapping[str, Mapping[str, Any]]
    hessenberg: np.ndarray
    final_true_residual_norm: float
    final_relative_residual: float
    audit: Mapping[str, Any]


class DiskBackedFlexibleGMRES:
    """Run one deterministic right flexible-GMRES cycle.

    ``action`` and ``pc`` receive finite complex128 vectors and must return
    finite complex128 vectors.  ``observer`` is called synchronously after a
    checkpoint's fresh action and residual have been computed.  Its
    ``solution``, ``action``, ``residual`` and ``rhs`` entries are borrowed
    until the callback returns; the solver retains only scalar checkpoint
    metadata.
    """

    def __init__(
        self,
        action: Callable[[np.ndarray], np.ndarray],
        pc: Callable[[np.ndarray], np.ndarray],
        *,
        max_steps: int = 200,
        checkpoints: tuple[int, ...] = (20, 100, 150, 200),
    ) -> None:
        if not callable(action) or not callable(pc):
            raise TypeError("action and pc must be callable")
        if not isinstance(max_steps, int) or not 1 <= max_steps <= 200:
            raise ValueError("max_steps must be an integer in [1, 200]")
        if not checkpoints or tuple(sorted(set(checkpoints))) != checkpoints:
            raise ValueError("checkpoints must be a sorted tuple of unique iterations")
        if any(not isinstance(value, int) or value < 1 for value in checkpoints):
            raise ValueError("checkpoint iterations must be positive integers")
        if checkpoints[-1] > max_steps:
            raise ValueError("the final checkpoint exceeds max_steps")
        self.action = action
        self.pc = pc
        self.max_steps = max_steps
        self.checkpoints = checkpoints

    def solve(
        self,
        rhs: np.ndarray,
        *,
        scratch_dir: str | Path,
        initial_solution: np.ndarray | None = None,
        observer: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> DiskBackedFlexibleGMRESResult:
        rhs_input = np.asarray(rhs)
        if rhs_input.ndim != 1 or rhs_input.dtype != _COMPLEX128:
            raise TypeError("rhs must be a complex128 vector")
        rows = rhs_input.shape[0]
        rhs_values = np.array(
            _require_vector(rhs_input, rows, "rhs"),
            dtype=_COMPLEX128,
            order="C",
            copy=True,
        )
        if initial_solution is None:
            x0 = np.zeros(rows, dtype=_COMPLEX128)
            initial_solution_provided = False
        else:
            x0 = np.array(
                _require_vector(initial_solution, rows, "initial_solution"),
                dtype=_COMPLEX128,
                order="C",
                copy=True,
            )
            initial_solution_provided = True
        if observer is not None and not callable(observer):
            raise TypeError("observer must be callable or None")

        scratch = Path(scratch_dir)
        scratch.mkdir(parents=False, exist_ok=False)
        v_store: RawPositionalColumnStore | None = None
        z_store: RawPositionalColumnStore | None = None
        action_count = 0
        pc_count = 0
        initial_action_count = 0
        observer_count = 0
        checkpoint_metadata: dict[str, dict[str, Any]] = {}
        breakdown_scale: float | None = None
        breakdown_threshold: float | None = None

        def apply_action(values: np.ndarray) -> np.ndarray:
            nonlocal action_count
            values = _require_vector(values, rows, "action input")
            output = np.asarray(self.action(values))
            action_count += 1
            return np.array(
                _require_vector(output, rows, "action output"),
                dtype=_COMPLEX128,
                order="C",
                copy=False,
            )

        def apply_pc(values: np.ndarray) -> np.ndarray:
            nonlocal pc_count
            values = _require_vector(values, rows, "pc input")
            output = np.asarray(self.pc(values))
            pc_count += 1
            return np.array(
                _require_vector(output, rows, "pc output"),
                dtype=_COMPLEX128,
                order="C",
                copy=False,
            )

        def make_audit(
            *,
            iterations: int,
            happy_breakdown: bool,
            hessenberg_rows: int,
        ) -> dict[str, Any]:
            assert v_store is not None
            assert z_store is not None
            vector_bytes = rows * _COMPLEX128_BYTES
            bounded_buffer_count = 12
            bounded_buffer_bytes = bounded_buffer_count * vector_bytes
            return {
                "algorithm": "right_flexible_gmres",
                "rows": rows,
                "dtype": "complex128",
                "max_steps": self.max_steps,
                "iterations": iterations,
                "checkpoint_iterations": list(self.checkpoints),
                "checkpoint_count": len(checkpoint_metadata),
                "observer_count": observer_count,
                "action_count": action_count,
                "pc_count": pc_count,
                "initial_action_count": initial_action_count,
                "orthogonalization_passes": 2,
                "happy_breakdown": happy_breakdown,
                "hessenberg_shape": [hessenberg_rows, iterations],
                "mmap": False,
                "basis_in_memory": False,
                "retained_full_vector_count": 1,
                "retained_full_vector_bytes": vector_bytes,
                "bounded_full_vector_buffer_count": bounded_buffer_count,
                "bounded_full_vector_bytes": bounded_buffer_bytes,
                "bounded_full_vector_limit_bytes": _FULL_VECTOR_BUFFER_LIMIT_BYTES,
                "bounded_full_vector_gate": bounded_buffer_bytes
                <= _FULL_VECTOR_BUFFER_LIMIT_BYTES,
                "scratch_bytes": v_store.allocated_bytes + z_store.allocated_bytes,
                "scratch_mmap": False,
                "scratch_basis_in_memory": False,
                "v_basis": v_store.audit(),
                "z_basis": z_store.audit(),
                "scratch_paths": {
                    "v_basis": str(v_store.path),
                    "z_basis": str(z_store.path),
                },
                "initial_solution_provided": initial_solution_provided,
                "checkpoint_set_complete": set(checkpoint_metadata)
                == {str(value) for value in self.checkpoints},
                "breakdown_rule": (
                    "64*eps*max(1,norm(A*z_j before orthogonalization))"
                ),
                "last_breakdown_scale": breakdown_scale,
                "last_breakdown_threshold": breakdown_threshold,
            }

        try:
            v_store = RawPositionalColumnStore(scratch / "v_basis.bin", rows, self.max_steps + 1)
            z_store = RawPositionalColumnStore(scratch / "z_basis.bin", rows, self.max_steps)

            rhs_norm = float(np.linalg.norm(rhs_values))
            if initial_solution_provided:
                initial_action = apply_action(x0)
                initial_action_count = 1
                residual = np.array(rhs_values, dtype=_COMPLEX128, copy=True)
                residual -= initial_action
                del initial_action
            else:
                residual = np.array(rhs_values, dtype=_COMPLEX128, copy=True)
            residual_norm = float(np.linalg.norm(residual))
            if residual_norm == 0.0:
                final_action = apply_action(x0)
                final_residual = np.array(rhs_values, dtype=_COMPLEX128, copy=True)
                final_residual -= final_action
                audit = make_audit(
                    iterations=0,
                    happy_breakdown=True,
                    hessenberg_rows=0,
                )
                return DiskBackedFlexibleGMRESResult(
                    solution=x0,
                    iterations=0,
                    happy_breakdown=True,
                    checkpoints=checkpoint_metadata,
                    hessenberg=np.empty((0, 0), dtype=_COMPLEX128),
                    final_true_residual_norm=float(np.linalg.norm(final_residual)),
                    final_relative_residual=0.0,
                    audit=audit,
                )

            hessenberg = np.zeros(
                (self.max_steps + 1, self.max_steps), dtype=_COMPLEX128
            )
            least_squares_rhs = np.zeros(self.max_steps + 1, dtype=_COMPLEX128)
            least_squares_rhs[0] = residual_norm
            v_current = np.array(residual / residual_norm, copy=True)
            v_store.write_column(0, v_current)
            v_read = np.empty(rows, dtype=_COMPLEX128)
            z_read = np.empty(rows, dtype=_COMPLEX128)
            iterations = 0
            happy_breakdown = False
            hessenberg_rows = 0
            final_checkpoint_payload: tuple[
                np.ndarray, np.ndarray, np.ndarray
            ] | None = None

            def reconstruct(
                columns: int,
                h_rows: int,
            ) -> tuple[np.ndarray, float]:
                matrix = hessenberg[:h_rows, :columns]
                coefficients = np.linalg.lstsq(
                    matrix,
                    least_squares_rhs[:h_rows],
                    rcond=None,
                )[0]
                candidate = np.array(x0, dtype=_COMPLEX128, copy=True)
                for column in range(columns):
                    z_store.read_column(column, z_read)
                    candidate += coefficients[column] * z_read
                estimate = float(
                    np.linalg.norm(
                        least_squares_rhs[:h_rows] - matrix @ coefficients
                    )
                )
                return candidate, estimate

            for column in range(self.max_steps):
                if final_checkpoint_payload is not None:
                    final_checkpoint_payload = None
                    del candidate, candidate_action, candidate_residual
                iterations = column + 1
                z_column = apply_pc(v_current)
                z_store.write_column(column, z_column)
                w = apply_action(z_column)
                operator_column_norm = float(np.linalg.norm(w))
                for _pass in range(2):
                    for previous in range(column + 1):
                        v_store.read_column(previous, v_read)
                        coefficient = np.vdot(v_read, w)
                        hessenberg[previous, column] += coefficient
                        w -= coefficient * v_read
                next_norm = float(np.linalg.norm(w))
                column_scale = max(1.0, operator_column_norm)
                column_threshold = _BREAKDOWN_MULTIPLIER * _FLOAT_EPS * column_scale
                hessenberg[column + 1, column] = next_norm
                if next_norm <= column_threshold:
                    breakdown_scale = column_scale
                    breakdown_threshold = column_threshold
                    happy_breakdown = True
                    hessenberg_rows = column + 1
                else:
                    hessenberg_rows = column + 2
                    v_current = np.array(w / next_norm, copy=True)
                    v_store.write_column(column + 1, v_current)

                if iterations in self.checkpoints:
                    candidate, estimate = reconstruct(
                        iterations,
                        hessenberg_rows,
                    )
                    candidate_action = apply_action(candidate)
                    candidate_residual = np.array(
                        rhs_values,
                        dtype=_COMPLEX128,
                        copy=True,
                    )
                    candidate_residual -= candidate_action
                    candidate_residual_norm = float(np.linalg.norm(candidate_residual))
                    relative = candidate_residual_norm / max(
                        rhs_norm, np.finfo(float).tiny
                    )
                    event = {
                        "iteration": iterations,
                        "solution": candidate,
                        "action": candidate_action,
                        "residual": candidate_residual,
                        "rhs": rhs_values,
                        "true_residual_norm": candidate_residual_norm,
                        "true_relative_residual": relative,
                        "estimated_residual_norm": estimate,
                    }
                    if observer is not None:
                        observer(event)
                        observer_count += 1
                    checkpoint_metadata[str(iterations)] = {
                        "iteration": iterations,
                        "true_residual_norm": candidate_residual_norm,
                        "true_relative_residual": relative,
                        "estimated_residual_norm": estimate,
                        "action_count": action_count,
                        "pc_count": pc_count,
                    }
                    if iterations == self.checkpoints[-1]:
                        final_checkpoint_payload = (
                            candidate,
                            candidate_action,
                            candidate_residual,
                        )
                    else:
                        del candidate, candidate_action, candidate_residual
                    del event

                if happy_breakdown:
                    break

            if (
                final_checkpoint_payload is not None
                and iterations == self.checkpoints[-1]
            ):
                final_solution, final_action, final_residual = final_checkpoint_payload
                final_norm = float(np.linalg.norm(final_residual))
            else:
                final_solution, _estimate = reconstruct(iterations, hessenberg_rows)
                final_action = apply_action(final_solution)
                final_residual = np.array(rhs_values, dtype=_COMPLEX128, copy=True)
                final_residual -= final_action
                final_norm = float(np.linalg.norm(final_residual))
            final_relative = final_norm / max(rhs_norm, np.finfo(float).tiny)
            audit = make_audit(
                iterations=iterations,
                happy_breakdown=happy_breakdown,
                hessenberg_rows=hessenberg_rows,
            )
            return DiskBackedFlexibleGMRESResult(
                solution=final_solution,
                iterations=iterations,
                happy_breakdown=happy_breakdown,
                checkpoints=checkpoint_metadata,
                hessenberg=np.array(
                    hessenberg[:hessenberg_rows, :iterations],
                    dtype=_COMPLEX128,
                    order="C",
                    copy=True,
                ),
                final_true_residual_norm=final_norm,
                final_relative_residual=final_relative,
                audit=audit,
            )
        finally:
            if z_store is not None:
                z_store.close()
            if v_store is not None:
                v_store.close()
