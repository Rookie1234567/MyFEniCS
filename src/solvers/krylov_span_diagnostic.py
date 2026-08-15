"""Streaming optimistic projection diagnostics for a disk-backed Krylov basis."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


BASIS_COLUMNS = 201
ROW_BLOCK = 4096
RANK_THRESHOLD_MULTIPLIER = 128.0
NORMAL_CLOSURE_LIMIT = 1.0e-11


def _vector(value: Any, rows: int, label: str) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.ndim != 1
        or array.shape != (rows,)
        or array.dtype != np.dtype(np.complex128)
        or not np.all(np.isfinite(array))
    ):
        raise ValueError(f"{label} must be finite complex128 with {rows} entries")
    return array


def _projection(
    gram_h: np.ndarray,
    h: np.ndarray,
    vector_norm: float,
    sigma_max: float,
    *,
    include_coefficients: bool = False,
) -> dict[str, Any]:
    coefficients = np.linalg.solve(gram_h, h)
    normal_error = gram_h @ coefficients - h
    closure = float(
        np.linalg.norm(normal_error)
        / max(sigma_max * sigma_max * np.linalg.norm(coefficients) + np.linalg.norm(h), np.finfo(float).tiny)
    )
    norm_squared = vector_norm * vector_norm
    captured = float(np.real(np.vdot(h, coefficients)))
    captured_ratio_raw = captured / max(norm_squared, np.finfo(float).tiny)
    if not np.isfinite(captured_ratio_raw) or not -1.0e-11 <= captured_ratio_raw <= 1.0 + 1.0e-11:
        result = {
            "finite": False,
            "normal_closure": closure,
            "captured_energy": captured,
            "captured_energy_ratio": captured_ratio_raw,
            "captured_energy_ratio_raw": captured_ratio_raw,
            "rho_full_energy_derived": float("nan"),
            "coefficient_norm": float(np.linalg.norm(coefficients)),
            "problems": ["captured_energy_range"],
        }
        if include_coefficients:
            result["_coefficients"] = coefficients
        return result
    captured_ratio = float(np.clip(captured_ratio_raw, 0.0, 1.0))
    result = {
        "finite": bool(np.isfinite(closure) and np.isfinite(captured) and np.isfinite(captured_ratio)),
        "normal_closure": closure,
        "captured_energy": captured_ratio * norm_squared,
        "captured_energy_ratio": captured_ratio,
        "captured_energy_ratio_raw": captured_ratio_raw,
        "rho_full_energy_derived": float(np.sqrt(1.0 - captured_ratio)),
        "coefficient_norm": float(np.linalg.norm(coefficients)),
    }
    if include_coefficients:
        result["_coefficients"] = coefficients
    return result


def _stream_projection_residual(
    basis: np.ndarray,
    residuals: Mapping[str, np.ndarray],
    coefficients: Mapping[str, np.ndarray],
    *,
    rows: int,
    columns: int,
    row_block: int,
) -> dict[str, Any]:
    """Compute direct ``||r - Vc||`` values with one bounded basis pass."""

    squared = {name: 0.0 for name in residuals}
    block_count = 0
    column_read_count = 0
    for start in range(0, rows, row_block):
        stop = min(start + row_block, rows)
        block = np.array(basis[:, start:stop], dtype=np.complex128, order="C", copy=True)
        if not np.all(np.isfinite(block)):
            raise ValueError("basis block is not finite")
        for name, vector in residuals.items():
            projected = coefficients[name] @ block
            remainder = vector[start:stop] - projected
            squared[name] += float(np.vdot(remainder, remainder).real)
        block_count += 1
        column_read_count += columns
    return {
        "squared": squared,
        "block_count": block_count,
        "column_read_count": column_read_count,
        "explicit_vector_temp_bytes": int(2 * row_block * np.dtype(np.complex128).itemsize),
    }


def analyze_v_basis(
    path: Path,
    residuals: Mapping[str, Any],
    *,
    rows: int,
    columns: int = BASIS_COLUMNS,
    row_block: int = ROW_BLOCK,
) -> dict[str, Any]:
    """Stream a fixed row-block Gram accumulation and optimistic projections.

    The file is C-order ``(columns, rows)`` complex128 data.  It is mapped
    read-only; only one row block and the small Gram/H vectors are retained.
    """

    if type(rows) is not int or rows <= 0 or type(columns) is not int or columns <= 0:
        raise ValueError("basis dimensions must be positive integers")
    if type(row_block) is not int or row_block <= 0:
        raise ValueError("row_block must be a positive integer")
    required = {"control_w5_iter200", "target_w7_cumulative400"}
    if not isinstance(residuals, Mapping) or set(residuals) != required:
        raise ValueError("W10A requires the fixed control and target residuals")
    vectors = {name: _vector(value, rows, name) for name, value in residuals.items()}
    expected_bytes = columns * rows * np.dtype(np.complex128).itemsize
    if Path(path).stat().st_size != expected_bytes:
        raise ValueError("basis file size does not match its fixed layout")
    basis = np.memmap(path, dtype=np.complex128, mode="r", shape=(columns, rows), order="C")
    gram = np.zeros((columns, columns), dtype=np.complex128)
    h = {name: np.zeros(columns, dtype=np.complex128) for name in required}
    block_count = 0
    column_read_count = 0
    for start in range(0, rows, row_block):
        stop = min(start + row_block, rows)
        block = np.array(basis[:, start:stop], dtype=np.complex128, order="C", copy=True)
        if not np.all(np.isfinite(block)):
            raise ValueError("basis block is not finite")
        gram += block.conj() @ block.T
        for name, vector in vectors.items():
            h[name] += block.conj() @ vector[start:stop]
        block_count += 1
        column_read_count += columns
    del block
    hermitian_defect = float(
        np.linalg.norm(gram - gram.conj().T)
        / max(np.linalg.norm(gram), np.finfo(float).tiny)
    )
    gram_hermitian = (gram + gram.conj().T) * 0.5
    eigenvalues = np.linalg.eigvalsh(gram_hermitian)
    eig_min = float(eigenvalues[0])
    eig_max = float(eigenvalues[-1])
    negative_eigenvalue_limit = 128.0 * np.finfo(float).eps * max(1.0, eig_max)
    gram_valid = bool(
        hermitian_defect <= NORMAL_CLOSURE_LIMIT
        and eig_min >= -negative_eigenvalue_limit
    )
    if gram_valid:
        singular_values = np.sqrt(np.maximum(eigenvalues, 0.0))
        sigma_max = float(singular_values[-1])
        threshold = RANK_THRESHOLD_MULTIPLIER * np.finfo(float).eps * sigma_max
        rank = int(np.count_nonzero(singular_values > threshold))
        condition = float(sigma_max / singular_values[0]) if singular_values[0] > 0 else float("inf")
    else:
        singular_values = np.full(columns, np.nan, dtype=float)
        threshold = float("nan")
        rank = 0
        condition = float("inf")
    audit = {
        "basis_path": str(Path(path).resolve()),
        "rows": rows,
        "columns": columns,
        "dtype": "complex128",
        "layout": "C-order columns-contiguous",
        "row_block": row_block,
        "explicit_copied_block_bytes": columns * row_block * 16,
        "explicit_copied_block_scope": "row-block copy only; conjugate and BLAS temporaries excluded",
        "block_count": block_count,
        "gram_column_read_count": column_read_count,
        "direct_projection_pass_count": 0,
        "basis_pass_count": 1,
        "column_read_count": column_read_count,
        "mmap": True,
        "basis_in_memory": False,
        "retained_heap_basis_bytes": 0,
        "mapped_file_bytes": int(expected_bytes),
        "gram_bytes": int(gram.nbytes),
    }
    result: dict[str, Any] = {
        "finite": bool(
            np.all(np.isfinite(gram))
            and np.all(np.isfinite(gram_hermitian))
            and np.all(np.isfinite(eigenvalues))
            and np.isfinite(hermitian_defect)
            and np.isfinite(eig_min)
            and np.isfinite(eig_max)
        ),
        "gram_valid": gram_valid,
        "rank": rank,
        "columns": columns,
        "singular_values": singular_values,
        "rank_threshold": threshold,
        "condition_number": condition,
        "gram_hermitian_defect": hermitian_defect,
        "eig_min": eig_min,
        "eig_max": eig_max,
        "negative_eigenvalue_limit": negative_eigenvalue_limit,
        "audit": audit,
        "measurements": {},
        "gram": gram,
        "gram_hermitian": gram_hermitian,
        "h": h,
        "pass": False,
        "problems": [],
    }
    if not result["finite"]:
        result["problems"] = ["nonfinite"]
        return result
    if hermitian_defect > NORMAL_CLOSURE_LIMIT:
        result["problems"] = ["gram_hermitian"]
        return result
    if eig_min < -negative_eigenvalue_limit:
        result["problems"] = ["negative_eigenvalue"]
        return result
    if not gram_valid:
        result["problems"] = ["gram"]
        return result
    if rank != columns:
        del basis
        result["problems"] = ["rank"]
        return result
    coefficients = {}
    for name, vector in vectors.items():
        item = _projection(
            gram_hermitian,
            h[name],
            float(np.linalg.norm(vector)),
            sigma_max,
            include_coefficients=True,
        )
        coefficients[name] = item.pop("_coefficients")
        result["measurements"][name] = item
    direct_first = _stream_projection_residual(
        basis, vectors, coefficients, rows=rows, columns=columns, row_block=row_block
    )
    direct_second = _stream_projection_residual(
        basis, vectors, coefficients, rows=rows, columns=columns, row_block=row_block
    )
    direct_exact = True
    for name, vector in vectors.items():
        norm = float(np.linalg.norm(vector))
        denominator = max(norm, np.finfo(float).tiny)
        first_squared = direct_first["squared"][name]
        second_squared = direct_second["squared"][name]
        first_rho = float(np.sqrt(max(first_squared, 0.0)) / denominator)
        second_rho = float(np.sqrt(max(second_squared, 0.0)) / denominator)
        exact = bool(
            np.array_equal(first_squared, second_squared)
            and np.array_equal(first_rho, second_rho)
        )
        direct_exact = direct_exact and exact
        item = result["measurements"][name]
        item.update(
            rho_full=first_rho,
            direct_residual_squared=first_squared,
            direct_repeat_rho_full=second_rho,
            direct_repeat_residual_squared=second_squared,
            direct_repeat_exact=exact,
        )
        item["finite"] = bool(
            item["finite"]
            and np.isfinite(first_squared)
            and np.isfinite(second_squared)
            and np.isfinite(first_rho)
            and np.isfinite(second_rho)
            and first_squared >= 0.0
            and second_squared >= 0.0
        )
    del basis
    result["audit"].update(
        basis_pass_count=3,
        direct_projection_pass_count=2,
        direct_column_read_count=direct_first["column_read_count"] + direct_second["column_read_count"],
        column_read_count=(
            result["audit"]["gram_column_read_count"]
            + direct_first["column_read_count"]
            + direct_second["column_read_count"]
        ),
        direct_projection_block_count=direct_first["block_count"],
        explicit_direct_vector_temp_bytes=direct_first["explicit_vector_temp_bytes"],
        explicit_direct_vector_temp_scope=(
            "one projected/remainder vector per residual and row block; conjugate and BLAS temporaries excluded"
        ),
    )
    result["pass"] = bool(
        direct_exact
        and all(item["finite"] and item["normal_closure"] <= NORMAL_CLOSURE_LIMIT for item in result["measurements"].values())
        and hermitian_defect <= NORMAL_CLOSURE_LIMIT
    )
    if not result["pass"]:
        result["problems"] = sorted(
            {
                problem
                for item in result["measurements"].values()
                for problem in item.get("problems", ["projection_closure"])
            }
        )
    return result


def project_from_gram(
    gram_h: np.ndarray, h: np.ndarray, vector_norm: float, sigma_max: float
) -> dict[str, Any]:
    """Recompute one scalar projection from an already accumulated Hermitian Gram."""

    return _projection(gram_h, h, vector_norm, sigma_max)


def add_actionable_projection(measurement: Mapping[str, Any], q_overlap_energy: float) -> dict[str, Any]:
    """Apply the fixed final-residual-direction removal to one full-span result."""

    if (
        not isinstance(measurement, Mapping)
        or measurement.get("finite") is not True
        or not np.isfinite(q_overlap_energy)
        or not -1.0e-11 <= q_overlap_energy <= 1.0 + 1.0e-11
    ):
        raise ValueError("projection measurement is incomplete")
    captured_ratio = float(measurement["captured_energy_ratio"])
    if not np.isfinite(captured_ratio) or not -1.0e-11 <= captured_ratio <= 1.0 + 1.0e-11:
        raise ValueError("captured energy is outside its fixed range")
    captured_ratio = float(np.clip(captured_ratio, 0.0, 1.0))
    captured_actionable_raw = captured_ratio - q_overlap_energy
    if not np.isfinite(captured_actionable_raw) or not -1.0e-11 <= captured_actionable_raw <= 1.0 + 1.0e-11:
        raise ValueError("captured actionable energy is outside its fixed range")
    captured_actionable_ratio = float(np.clip(captured_actionable_raw, 0.0, 1.0))
    q_overlap_energy = float(np.clip(q_overlap_energy, 0.0, 1.0))
    rho_optimistic = float(np.sqrt(max(1.0 - captured_actionable_ratio, 0.0)))
    result = dict(measurement)
    result.update(
        q_overlap_energy_ratio=q_overlap_energy,
        captured_actionable_energy_ratio=captured_actionable_ratio,
        rho_optimistic=rho_optimistic,
    )
    return result
