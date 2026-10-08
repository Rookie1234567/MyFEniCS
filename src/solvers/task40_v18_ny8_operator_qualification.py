"""Complete native FE oracle for a Ny-periodic p6 reference operator."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from typing import Any

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

MAPPING_LIMIT = 1.0e-12
OPERATOR_LIMIT = 1.0e-11


def _finite_csr(value: Any, *, shape: tuple[int, int], label: str) -> sparse.csr_matrix:
    if (
        sparse.isspmatrix_csr(value)
        and value.dtype == np.dtype(np.complex128)
        and value.has_canonical_format
        and value.has_sorted_indices
    ):
        matrix = value
    else:
        matrix = sparse.csr_matrix(value, dtype=np.complex128, copy=True)
        matrix.sum_duplicates()
        matrix.sort_indices()
    if matrix.shape != shape or not np.isfinite(matrix.data).all():
        raise ValueError(f"{label} must be finite complex128 CSR with shape {shape}")
    return matrix


def _csr_payload_bytes(matrix: sparse.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _csr_shares_buffers(left: sparse.csr_matrix, right: sparse.csr_matrix) -> bool:
    return any(
        np.shares_memory(left_buffer, right_buffer)
        for left_buffer in (left.data, left.indices, left.indptr)
        for right_buffer in (right.data, right.indices, right.indptr)
    )


def _frobenius(matrix: sparse.spmatrix | np.ndarray) -> float:
    values = np.asarray(matrix.data if sparse.issparse(matrix) else matrix).reshape(-1)
    squared = np.longdouble(0.0)
    chunk = 1 << 18
    for start in range(0, len(values), chunk):
        magnitude = np.abs(values[start : start + chunk]).astype(np.longdouble, copy=False)
        squared += np.sum(magnitude * magnitude, dtype=np.longdouble)
    return float(np.sqrt(squared))


def _imaginary_nonzero_count(values: np.ndarray) -> int:
    array = np.asarray(values).reshape(-1)
    count = 0
    chunk = 1 << 18
    for start in range(0, len(array), chunk):
        count += int(np.count_nonzero(array[start : start + chunk].imag))
    return count


def _owned_array_or_copy(values: Any, *, dtype: Any) -> np.ndarray:
    """Reuse a matching owning NumPy array; copy only borrowed or mismatched data."""
    expected_dtype = np.dtype(dtype)
    array = np.asarray(values)
    if array.dtype == expected_dtype and array.flags.owndata:
        return array
    return np.array(array, dtype=expected_dtype, copy=True)


def _csr_product_nnz_upper(
    left: sparse.csr_matrix,
    right: sparse.csr_matrix,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None,
    label: str,
) -> tuple[int, int]:
    """Count the row-wise union of reachable output columns before multiplication."""
    if left.shape[1] != right.shape[0]:
        raise ValueError("sparse product dimensions do not agree")
    right_row_nnz = np.diff(right.indptr)
    max_row_contributions = 0
    for row in range(left.shape[0]):
        start, stop = int(left.indptr[row]), int(left.indptr[row + 1])
        if stop > start:
            contributions = int(
                np.sum(right_row_nnz[left.indices[start:stop]], dtype=np.int64)
            )
            max_row_contributions = max(max_row_contributions, contributions)
    if allocation_gate is not None:
        allocation_gate(
            f"{label}_reachable_column_count_workspace",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": int(max_row_contributions * 16),
                "max_single_output_row_product_contributions": max_row_contributions,
                "right_column_count": int(right.shape[1]),
                "rowwise_reachable_column_union_preflight": True,
            },
        )
    upper = 0
    for row in range(left.shape[0]):
        start, stop = int(left.indptr[row]), int(left.indptr[row + 1])
        if stop <= start:
            continue
        cols = left.indices[start:stop]
        segments = [
            right.indices[int(right.indptr[col]) : int(right.indptr[col + 1])]
            for col in cols
            if right.indptr[col + 1] > right.indptr[col]
        ]
        if segments:
            support = segments[0] if len(segments) == 1 else np.concatenate(segments)
            upper += int(len(np.unique(support)))
    return upper, max_row_contributions


def _admit_sparse_product(
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None,
    label: str,
    left: sparse.csr_matrix,
    right: sparse.csr_matrix,
    structural_upper_cache: dict[str, tuple[int, int]] | None = None,
    cache_key: str | None = None,
) -> int:
    cached = (
        structural_upper_cache.get(cache_key)
        if structural_upper_cache is not None and cache_key is not None
        else None
    )
    if cached is None:
        upper_nnz, max_row_contributions = _csr_product_nnz_upper(
            left,
            right,
            allocation_gate=allocation_gate,
            label=label,
        )
        if structural_upper_cache is not None and cache_key is not None:
            structural_upper_cache[cache_key] = (upper_nnz, max_row_contributions)
    else:
        upper_nnz, max_row_contributions = cached
    if allocation_gate is not None:
        row_pointer_bytes = (left.shape[0] + 1) * np.dtype(np.int32).itemsize
        output_upper_bytes = upper_nnz * (
            np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize
        ) + row_pointer_bytes
        allocation_gate(
            label,
            {
                "additional_payload_bytes": int(output_upper_bytes),
                "workspace_bytes": int(
                    (right.shape[1] + max_row_contributions) * 24
                ),
                "product_contribution_nnz_upper": int(upper_nnz),
                "left_shape": list(left.shape),
                "left_nnz": int(left.nnz),
                "right_shape": list(right.shape),
                "right_nnz": int(right.nnz),
                "output_columns_counted_as_rowwise_reachable_union": True,
            },
        )
    return upper_nnz


def _csr_pattern_sha256(matrix: sparse.csr_matrix) -> str:
    h = sha256()
    h.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    for values in (matrix.indptr, matrix.indices):
        h.update(memoryview(np.ascontiguousarray(values)).cast("B"))
    return h.hexdigest()


def build_complete_q_primal_lift(
    entities: Any,
    layout: Any,
    q: int,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> sparse.csr_matrix:
    """Build one exact sparse native lift from q-cell coordinates to FE rows."""
    ny = int(entities.ny)
    width = int(entities.width)
    rows_count = int(len(entities.independent))
    if type(q) is not int or q not in range(ny) or rows_count != ny * width:
        raise ValueError("q lift requires one complete profile branch and native FE inventory")
    if int(layout.ny) != ny or int(layout.width) != width:
        raise ValueError("q lift and full FE modal layout identities disagree")
    expected_keys = {(orbit, base) for orbit in range(ny) for base in entities.bases}
    if set(entities.records) != expected_keys:
        raise ValueError("q lift lacks one actual native transform for every cell-orbit entity")
    block_nnz = sum(
        int(np.count_nonzero(np.asarray(entities.records[key][1])))
        for key in expected_keys
    )
    int32_limit = int(np.iinfo(np.int32).max)
    if rows_count > int32_limit or width > int32_limit or block_nnz > int32_limit:
        raise OverflowError("complete q lift shape or NNZ exceeds the qualified PetscInt range")
    if allocation_gate is not None:
        allocation_gate(
            "task40_v18_complete_q_native_lift",
            {
                "additional_payload_bytes": int(
                    block_nnz * 44
                    + 2 * (rows_count + 1) * np.dtype(np.int32).itemsize
                ),
                "workspace_bytes": int(block_nnz * 24),
                "q": q,
                "native_rows": rows_count,
                "q_rows": width,
                "complete_entity_blocks": len(expected_keys),
                "native_index_dtype": np.dtype(np.int32).str,
                "int64_count_preflight_before_allocation": True,
            },
        )
    row_indices = np.empty(block_nnz, dtype=np.int32)
    column_indices = np.empty(block_nnz, dtype=np.int32)
    values = np.empty(block_nnz, dtype=np.complex128)
    cursor = 0
    for orbit in range(ny):
        fourier = complex(layout.cell_dft[orbit, q])
        for base in entities.bases:
            native_rows, raw_transform = entities.records[(orbit, base)]
            native_rows = np.asarray(native_rows, dtype=np.int64).reshape(-1)
            transform = np.asarray(raw_transform, dtype=np.complex128)
            first, size = map(int, entities.slots[base])
            if (
                transform.shape != (size, size)
                or native_rows.shape != (size,)
                or (len(native_rows) and (native_rows.min() < 0 or native_rows.max() >= rows_count))
                or not np.isfinite(transform).all()
            ):
                raise ValueError("actual native entity transform is incomplete or non-finite")
            local_rows, local_columns = np.nonzero(transform)
            count = len(local_rows)
            stop = cursor + count
            row_indices[cursor:stop] = native_rows[local_rows]
            column_indices[cursor:stop] = first + local_columns
            values[cursor:stop] = transform[local_rows, local_columns] * fourier
            cursor = stop
    if cursor != block_nnz:
        raise RuntimeError("complete q lift contribution count changed during construction")
    result = sparse.coo_matrix(
        (values, (row_indices, column_indices)),
        shape=(rows_count, width),
        dtype=np.complex128,
    ).tocsr()
    result.sum_duplicates()
    result.sort_indices()
    if not np.isfinite(result.data).all():
        raise ValueError("complete q lift contains non-finite coefficients")
    return result


def _mode_q_inventory(
    sectors: Sequence[Any], mode_count: int, q_count: int
) -> tuple[np.ndarray, list[list[int]]]:
    assigned = np.full(mode_count, -1, dtype=np.int16)
    owners = np.zeros(mode_count, dtype=np.int8)
    for sector in sectors:
        qids = tuple(map(int, sector.global_q_indices))
        original = np.asarray(sector.original_mode_indices, dtype=np.int64)
        branches = np.asarray(sector.local_branch_indices, dtype=np.int64)
        if branches.shape != original.shape or len(qids) != 2:
            raise ValueError("each two-cell twist must expose exactly its two q branches")
        if len(original) and (original.min() < 0 or original.max() >= mode_count):
            raise ValueError("twist mode inventory contains an out-of-range ordered mode")
        for branch, q in enumerate(qids):
            selected = original[branches == branch]
            if q not in range(q_count) or np.any(assigned[selected] != -1):
                raise ValueError("ordered modes are duplicated or assigned outside Ny")
            assigned[selected] = q
            owners[selected] += 1
    if not np.all(owners == 1) or np.any(assigned < 0):
        raise ValueError("all ordered physical modes must be assigned once across all q branches")
    by_q = [np.flatnonzero(assigned == q).astype(np.int64) for q in range(q_count)]
    return assigned, [values.tolist() for values in by_q]


def _carrier_coupling_matrices(
    carrier: Any,
    entities: Any,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None,
) -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    entries = tuple(carrier.entries)
    row_count = int(len(entities.independent))
    mode_count = len(entries)
    total_c_nnz = sum(len(entry.coupling_rows) for entry in entries)
    total_d_nnz = sum(len(entry.projection_rows) for entry in entries)
    if allocation_gate is not None:
        total_raw_nnz = int(total_c_nnz + total_d_nnz)
        allocation_gate(
            "task40_v18_full_carrier_C_D_sparse_construction",
            {
                "additional_payload_bytes": int(
                    total_raw_nnz * 68
                    + 2 * (row_count + mode_count + 2) * np.dtype(np.int32).itemsize
                ),
                "workspace_bytes": int(total_raw_nnz * 24),
                "raw_C_support_nnz": int(total_c_nnz),
                "raw_D_support_nnz": int(total_d_nnz),
                "carrier_mode_count": mode_count,
                "construction_includes_support_lists_concatenation_and_CSR": True,
            },
        )
    independent = np.asarray(entities.independent, dtype=np.int64)
    global_rows = int(carrier.global_rows)
    if independent.shape != (row_count,) or (len(independent) and independent[-1] >= global_rows):
        raise ValueError("actual carrier and independent native FE row identities disagree")
    if len(np.unique(independent)) != row_count:
        raise ValueError("native FE independent rows are not unique")
    h_values = np.asarray([entry.normalization_h for entry in entries], dtype=np.float64)
    if h_values.shape != (mode_count,) or not np.isfinite(h_values).all() or np.any(h_values <= 0):
        raise ValueError("all ordered modes must retain positive finite original H")
    inverse_sqrt_h = 1.0 / np.sqrt(h_values)
    coupling_rows: list[np.ndarray] = []
    coupling_columns: list[np.ndarray] = []
    coupling_values: list[np.ndarray] = []
    projection_rows: list[np.ndarray] = []
    projection_columns: list[np.ndarray] = []
    projection_values: list[np.ndarray] = []
    for mode, entry in enumerate(entries):
        c_global = np.asarray(entry.coupling_rows, dtype=np.int64)
        d_global = np.asarray(entry.projection_rows, dtype=np.int64)
        c_positions = np.searchsorted(independent, c_global)
        d_positions = np.searchsorted(independent, d_global)
        if (
            (len(c_global) and (np.any(c_positions >= row_count) or not np.array_equal(independent[c_positions], c_global)))
            or (len(d_global) and (np.any(d_positions >= row_count) or not np.array_equal(independent[d_positions], d_global)))
        ):
            raise ValueError("carrier C/D support must lie on actual independent FE rows")
        c_values = np.asarray(entry.coupling_values, dtype=np.complex128)
        d_values = np.asarray(entry.projection_values, dtype=np.complex128)
        if (
            c_values.shape != c_global.shape
            or d_values.shape != d_global.shape
            or not np.isfinite(c_values).all()
            or not np.isfinite(d_values).all()
        ):
            raise ValueError("carrier C/D values do not match their sparse native supports")
        coupling_rows.append(c_positions.astype(np.int32, copy=False))
        coupling_columns.append(np.full(len(c_positions), mode, dtype=np.int32))
        coupling_values.append(c_values * inverse_sqrt_h[mode])
        projection_rows.append(np.full(len(d_positions), mode, dtype=np.int32))
        projection_columns.append(d_positions.astype(np.int32, copy=False))
        projection_values.append(d_values * inverse_sqrt_h[mode])
    c_row = np.concatenate(coupling_rows) if coupling_rows else np.empty(0, dtype=np.int32)
    c_col = np.concatenate(coupling_columns) if coupling_columns else np.empty(0, dtype=np.int32)
    c_val = np.concatenate(coupling_values) if coupling_values else np.empty(0, dtype=np.complex128)
    d_row = np.concatenate(projection_rows) if projection_rows else np.empty(0, dtype=np.int32)
    d_col = np.concatenate(projection_columns) if projection_columns else np.empty(0, dtype=np.int32)
    d_val = np.concatenate(projection_values) if projection_values else np.empty(0, dtype=np.complex128)
    coupling = sparse.coo_matrix(
        (c_val, (c_row, c_col)), shape=(row_count, mode_count), dtype=np.complex128
    ).tocsr()
    projection = sparse.coo_matrix(
        (d_val, (d_row, d_col)), shape=(mode_count, row_count), dtype=np.complex128
    ).tocsr()
    coupling.sum_duplicates()
    projection.sum_duplicates()
    return coupling, projection, h_values


def _static_condense_augmented_q(
    q_matrix: sparse.csr_matrix,
    entities: Any,
    q_mode_count: int,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None,
    q: int,
    column_batch: int = 32,
) -> sparse.csr_matrix:
    width = int(entities.width)
    trace_slots = []
    interior_slots = []
    for base in entities.bases:
        first, size = map(int, entities.slots[base])
        target = trace_slots if int(base[0]) in (1, 2) else interior_slots if int(base[0]) == 3 else None
        if target is None:
            raise ValueError("native p6 entity map contains an unsupported geometric dimension")
        target.extend(range(first, first + size))
    trace = np.asarray(trace_slots, dtype=np.int32)
    interior = np.asarray(interior_slots, dtype=np.int32)
    if (
        len(trace) + len(interior) != width
        or len(np.unique(np.concatenate((trace, interior)))) != width
        or len(interior) == 0
        or q_matrix.shape != (width + q_mode_count, width + q_mode_count)
    ):
        raise ValueError("complete q augmented FE/trace/interior partition does not close")
    retained = np.concatenate((trace, width + np.arange(q_mode_count, dtype=np.int32)))
    dense_schur_nnz_upper = int(len(retained) * len(retained))
    dense_schur_payload_upper = int(
        dense_schur_nnz_upper
        * (np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize)
        + (len(retained) + 1) * np.dtype(np.int32).itemsize
    )
    submatrix_payload_upper = int(
        q_matrix.nnz
        * (np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize)
        + 4 * (width + q_mode_count + 1) * np.dtype(np.int32).itemsize
    )
    dense_lu_payload_upper = int(
        2
        * len(interior)
        * len(interior)
        * (np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize)
    )
    lu_workspace_upper = int(
        len(interior) * len(interior) * np.dtype(np.complex128).itemsize
    )
    batch_workspace_upper = int(
        column_batch
        * (2 * len(interior) + 4 * len(retained))
        * np.dtype(np.complex128).itemsize
    )
    estimate = int(
        submatrix_payload_upper
        + dense_lu_payload_upper
        + 2 * dense_schur_payload_upper
        + batch_workspace_upper
    )
    if allocation_gate is not None:
        allocation_gate(
            "task40_v18_independent_global_interior_schur",
            {
                "additional_payload_bytes": estimate,
                "workspace_bytes": lu_workspace_upper,
                "q": q,
                "interior_rows": int(len(interior)),
                "retained_trace_and_port_rows": int(len(retained)),
                "column_batch": column_batch,
                "independent_global_q_schur": True,
                "submatrix_payload_upper_bytes": submatrix_payload_upper,
                "dense_superlu_factor_payload_upper_bytes": dense_lu_payload_upper,
                "dense_superlu_workspace_upper_bytes": lu_workspace_upper,
                "dense_schur_csr_payload_upper_bytes": dense_schur_payload_upper,
                "columns_plus_hstack_overlap_reserved": True,
                "batched_rhs_solve_workspace_upper_bytes": batch_workspace_upper,
            },
        )
    A_ii = q_matrix[interior, :][:, interior].tocsc()
    A_ir = q_matrix[interior, :][:, retained].tocsc()
    A_ri = q_matrix[retained, :][:, interior].tocsr()
    A_rr = q_matrix[retained, :][:, retained].tocsr()
    factor = splu(A_ii)
    columns = []
    for start in range(0, len(retained), column_batch):
        stop = min(start + column_batch, len(retained))
        rhs = A_ir[:, start:stop].toarray()
        solved = factor.solve(rhs)
        correction = np.asarray(A_ri @ solved, dtype=np.complex128)
        block = A_rr[:, start:stop].toarray() - correction
        if not np.isfinite(block).all():
            raise FloatingPointError(f"q={q} independent static condensation produced non-finite entries")
        columns.append(sparse.csr_matrix(block, dtype=np.complex128))
        del rhs, solved, correction, block
    del factor, A_ii, A_ir, A_ri, A_rr
    result = sparse.hstack(columns, format="csr", dtype=np.complex128)
    result.sum_duplicates()
    result.sort_indices()
    return result


def qualify_complete_ny_reference_operator(
    *,
    volume_matrix: Any,
    entities: Any,
    layout: Any,
    carrier: Any,
    sectors: Sequence[Any],
    candidate_q_matrices: Mapping[int, Any],
    expected_q_port_counts: Sequence[int],
    allocation_gate: Callable[[str, Mapping[str, Any]], None] | None = None,
    tolerance: float = OPERATOR_LIMIT,
) -> dict[str, Any]:
    """Check every complete native FE/port q block against independent assembly.

    The oracle starts from one independently assembled full native FE volume
    matrix and the original sparse C/D/H carrier. It applies the actual
    entity-moment/Fourier congruence, visits every ordered q block, measures
    the complete off-diagonal Frobenius norm, then statically condenses each
    diagonal q block using a separate global sparse interior solve. Production
    candidate matrices are built from local cell tensors and local Schur data.
    """
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("complete operator tolerance must be finite and positive")
    ny = int(entities.ny)
    width = int(entities.width)
    native_rows = int(len(entities.independent))
    if (
        ny < 2
        or width * ny != native_rows
        or int(layout.ny) != ny
        or int(layout.width) != width
        or set(map(int, candidate_q_matrices)) != set(range(ny))
        or len(expected_q_port_counts) != ny
    ):
        raise ValueError("complete operator oracle requires every q matrix and native FE row")
    volume = _finite_csr(volume_matrix, shape=(native_rows, native_rows), label="full native FE volume matrix")
    carrier = carrier
    mode_count = len(carrier.entries)
    mode_q, mode_indices_by_q = _mode_q_inventory(sectors, mode_count, ny)
    q_port_counts = [len(indices) for indices in mode_indices_by_q]
    if q_port_counts != list(map(int, expected_q_port_counts)):
        raise ValueError(f"actual full FE q mode inventory differs from profile: {q_port_counts}")
    if set(map(int, candidate_q_matrices)) != set(range(ny)):
        raise ValueError("candidate q matrix mapping is not complete")
    candidates = {
        q: _finite_csr(
            candidate_q_matrices[q],
            shape=(int(candidate_q_matrices[q].shape[0]), int(candidate_q_matrices[q].shape[1])),
            label=f"candidate q={q} Schur matrix",
        )
        for q in range(ny)
    }
    coupling, projection, h_values = _carrier_coupling_matrices(
        carrier, entities, allocation_gate=allocation_gate
    )
    if mode_count != int(sum(q_port_counts)) or coupling.shape != (native_rows, mode_count):
        raise ValueError("complete FE C/D/H carrier inventory does not close")

    diagonal_norms: dict[int, float] = {}
    offdiagonal_squared: dict[tuple[int, int], np.longdouble] = {}
    offdiagonal_components: dict[str, dict[str, float]] = {}
    schur_errors: dict[int, float] = {}
    schur_norms: dict[int, dict[str, float]] = {}
    block_shapes: dict[str, list[int]] = {}
    q4_rhs_norm = None
    nonhermitian_relative: dict[int, float] = {}
    full_q_block_coverage = 0
    ny2 = ny * ny
    product_upper_cache: dict[str, tuple[int, int]] = {}
    for q in range(ny):
        Uq = build_complete_q_primal_lift(entities, layout, q, allocation_gate=allocation_gate)
        Uq_pattern = _csr_pattern_sha256(Uq)
        _admit_sparse_product(
            allocation_gate,
            "task40_v18_full_volume_times_q_lift",
            volume,
            Uq,
            structural_upper_cache=product_upper_cache,
            cache_key=f"volume_times_q_lift:{Uq_pattern}",
        )
        volume_times_Uq = volume @ Uq
        volume_times_Uq_pattern = _csr_pattern_sha256(volume_times_Uq)
        q_modes = np.asarray(mode_indices_by_q[q], dtype=np.int64)
        q_c_nnz_upper = sum(
            len(carrier.entries[int(mode)].coupling_rows) for mode in q_modes
        )
        if allocation_gate is not None:
            allocation_gate(
                "task40_v18_q_carrier_column_slice",
                {
                    "additional_payload_bytes": int(
                        q_c_nnz_upper * 20
                        + (native_rows + 1) * np.dtype(np.int32).itemsize
                    ),
                    "workspace_bytes": int(q_c_nnz_upper * 24),
                    "q": q,
                    "q_modes": int(len(q_modes)),
                    "raw_C_support_nnz_upper": int(q_c_nnz_upper),
                },
            )
        coupling_q = coupling[:, q_modes].tocsr()
        diagonal_q_augmented: sparse.csr_matrix | None = None
        diagonal_q_shared_inputs: dict[str, bool] | None = None
        for p in range(ny):
            Up = Uq if p == q else build_complete_q_primal_lift(
                entities, layout, p, allocation_gate=allocation_gate
            )
            if allocation_gate is not None:
                allocation_gate(
                    "task40_v18_q_lift_adjoint_CSR",
                    {
                        "additional_payload_bytes": int(Up.nnz * 20 + (width + 1) * 4),
                        "workspace_bytes": int(Up.nnz * 16),
                        "p": p,
                        "q": q,
                        "q_lift_nnz": int(Up.nnz),
                    },
                )
            Up_h = Up.getH().tocsr()
            Up_pattern = _csr_pattern_sha256(Up_h)
            _admit_sparse_product(
                allocation_gate,
                "task40_v18_complete_FE_volume_q_block",
                Up_h,
                volume_times_Uq,
                structural_upper_cache=product_upper_cache,
                cache_key=(
                    f"complete_FE_q_block:{Up_pattern}:"
                    f"{volume_times_Uq_pattern}"
                ),
            )
            volume_block = (Up_h @ volume_times_Uq).tocsr()
            _admit_sparse_product(
                allocation_gate,
                "task40_v18_complete_left_C_q_block",
                Up_h,
                coupling_q,
                structural_upper_cache=product_upper_cache,
                cache_key=(
                    f"complete_C_q_block:{Up_pattern}:{q}:"
                    f"{_csr_pattern_sha256(coupling_q)}"
                ),
            )
            C_block = (Up_h @ coupling_q).tocsr()
            p_modes = np.asarray(mode_indices_by_q[p], dtype=np.int64)
            p_d_nnz_upper = sum(
                len(carrier.entries[int(mode)].projection_rows) for mode in p_modes
            )
            if allocation_gate is not None:
                allocation_gate(
                    "task40_v18_q_projection_row_slice",
                    {
                        "additional_payload_bytes": int(
                            p_d_nnz_upper * 20 + (len(p_modes) + 1) * 4
                        ),
                        "workspace_bytes": int(p_d_nnz_upper * 24),
                        "p": p,
                        "q": q,
                        "p_modes": int(len(p_modes)),
                        "raw_D_support_nnz_upper": int(p_d_nnz_upper),
                    },
                )
            projection_p = projection[p_modes, :].tocsr()
            _admit_sparse_product(
                allocation_gate,
                "task40_v18_complete_right_D_q_block",
                projection_p,
                Uq,
                structural_upper_cache=product_upper_cache,
                cache_key=(
                    f"complete_D_q_block:{p}:{_csr_pattern_sha256(projection_p)}:"
                    f"{Uq_pattern}"
                ),
            )
            D_block = (projection_p @ Uq).tocsr()
            if (
                volume_block.shape != (width, width)
                or C_block.shape != (width, len(q_modes))
                or D_block.shape != (len(p_modes), width)
                or not np.isfinite(volume_block.data).all()
                or not np.isfinite(C_block.data).all()
                or not np.isfinite(D_block.data).all()
            ):
                raise ValueError("a complete FE/C/D q block has an invalid shape or value")
            block_shapes[f"{p}{q}"] = [width + len(p_modes), width + len(q_modes)]
            full_q_block_coverage += 1
            volume_norm = _frobenius(volume_block)
            c_norm = _frobenius(C_block)
            d_norm = _frobenius(D_block)
            if p == q:
                port_identity_norm_sq = np.longdouble(len(q_modes))
                diagonal_norm_sq = (
                    np.longdouble(volume_norm) ** 2
                    + np.longdouble(c_norm) ** 2
                    + np.longdouble(d_norm) ** 2
                    + port_identity_norm_sq
                )
                diagonal_norms[q] = float(np.sqrt(diagonal_norm_sq))
                q_augmented_nnz_upper = int(
                    volume_block.nnz + C_block.nnz + D_block.nnz + len(q_modes)
                )
                if allocation_gate is not None:
                    allocation_gate(
                        "task40_v18_diagonal_augmented_q_block",
                        {
                            "additional_payload_bytes": int(
                                q_augmented_nnz_upper * 44
                                + (width + len(q_modes) + 1) * 4
                            ),
                            "workspace_bytes": int(q_augmented_nnz_upper * 24),
                            "q": q,
                            "augmented_q_nnz_upper": q_augmented_nnz_upper,
                        },
                    )
                diagonal_q_augmented = sparse.bmat(
                    [
                        [volume_block, C_block],
                        [D_block, -sparse.eye(len(q_modes), dtype=np.complex128, format="csr")],
                    ],
                    format="csr",
                    dtype=np.complex128,
                )
                diagonal_q_augmented.sum_duplicates()
                diagonal_q_augmented.sort_indices()
                if diagonal_q_augmented.shape != (
                    width + len(q_modes),
                    width + len(q_modes),
                ):
                    raise ValueError(f"q={q} independent augmented FE/port block shape mismatch")
                diagonal_q_shared_inputs = {
                    "q_augmented_shares_volume_times_Uq_buffers": _csr_shares_buffers(
                        diagonal_q_augmented, volume_times_Uq
                    ),
                    "q_augmented_shares_Uq_buffers": _csr_shares_buffers(
                        diagonal_q_augmented, Uq
                    ),
                    "q_augmented_shares_coupling_q_buffers": _csr_shares_buffers(
                        diagonal_q_augmented, coupling_q
                    ),
                }
                if any(diagonal_q_shared_inputs.values()):
                    raise ValueError(
                        "independent q augmented CSR unexpectedly borrows a released q owner"
                    )
                if allocation_gate is not None:
                    allocation_gate(
                        "task40_v18_nonhermitian_witness_difference",
                        {
                            "additional_payload_bytes": int(
                                2 * diagonal_q_augmented.nnz * 20
                                + (diagonal_q_augmented.shape[0] + 1) * 4
                            ),
                            "workspace_bytes": int(diagonal_q_augmented.nnz * 24),
                            "q": q,
                            "augmented_q_nnz": int(diagonal_q_augmented.nnz),
                        },
                    )
                actual_nonhermitian = _frobenius(
                    diagonal_q_augmented - diagonal_q_augmented.getH()
                )
                nonhermitian_relative[q] = actual_nonhermitian / max(
                    diagonal_norms[q], np.finfo(float).tiny
                )
                if q == 4 and not len(q_modes):
                    if allocation_gate is not None:
                        allocation_gate(
                            "task40_v18_q4_nonzero_FE_rhs_witness",
                            {
                                "additional_payload_bytes": int(width * 20 + 4),
                                "workspace_bytes": int(width * 8),
                                "q": q,
                                "FE_basis_rows": width,
                            },
                        )
                    q4_rhs_norm = _frobenius(volume_block.getcol(0))
            else:
                off_sq = (
                    np.longdouble(volume_norm) ** 2
                    + np.longdouble(c_norm) ** 2
                    + np.longdouble(d_norm) ** 2
                )
                offdiagonal_squared[p, q] = off_sq
                offdiagonal_components[f"{p}{q}"] = {
                    "FE_volume_frobenius": volume_norm,
                    "left_C_over_sqrt_H_frobenius": c_norm,
                    "right_D_over_sqrt_H_frobenius": d_norm,
                    "complete_augmented_block_frobenius": float(np.sqrt(off_sq)),
                }
            del volume_block, C_block, D_block, projection_p, Up_h, Up
        if diagonal_q_augmented is None:
            raise ValueError(f"q={q} complete diagonal FE/port block was not constructed")
        if diagonal_q_shared_inputs is None:
            raise ValueError(f"q={q} diagonal backing independence was not checked")
        owner_payloads = {
            "volume_times_Uq_csr_payload_bytes": _csr_payload_bytes(volume_times_Uq),
            "volume_times_Uq_csr_component_buffers_own_data": all(
                buffer.flags.owndata
                for buffer in (
                    volume_times_Uq.data,
                    volume_times_Uq.indices,
                    volume_times_Uq.indptr,
                )
            ),
            "Uq_csr_payload_bytes": _csr_payload_bytes(Uq),
            "Uq_csr_component_buffers_own_data": all(
                buffer.flags.owndata for buffer in (Uq.data, Uq.indices, Uq.indptr)
            ),
            "coupling_q_csr_payload_bytes": _csr_payload_bytes(coupling_q),
            "coupling_q_csr_component_buffers_own_data": all(
                buffer.flags.owndata
                for buffer in (coupling_q.data, coupling_q.indices, coupling_q.indptr)
            ),
            "diagonal_q_augmented_csr_payload_bytes": _csr_payload_bytes(
                diagonal_q_augmented
            ),
            "diagonal_q_augmented_csr_component_buffers_own_data": all(
                buffer.flags.owndata
                for buffer in (
                    diagonal_q_augmented.data,
                    diagonal_q_augmented.indices,
                    diagonal_q_augmented.indptr,
                )
            ),
        }
        lifecycle_facts = {
            "q": q,
            "all_p_blocks_completed": True,
            "p_blocks_completed": int(ny),
            "full_q_block_coverage_for_q": int(ny),
            "last_use_volume_times_Uq": f"complete FE volume block p={ny - 1}, q={q}",
            "last_use_Uq": f"complete right-D block p={ny - 1}, q={q}",
            "last_use_coupling_q": f"complete left-C block p={ny - 1}, q={q}",
            "per_p_temporary_views_released": [
                "projection_p",
                "Up_h",
                "Up",
                "volume_block",
                "C_block",
                "D_block",
            ],
            **diagonal_q_shared_inputs,
            **owner_payloads,
        }
        if allocation_gate is not None:
            allocation_gate(
                "task40_v18_q_product_last_use_before_release",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 0,
                    "lifecycle_state": "all p blocks complete; local q owners still live",
                    **lifecycle_facts,
                },
            )
        del volume_times_Uq, Uq, coupling_q
        if allocation_gate is not None:
            allocation_gate(
                "task40_v18_q_product_released_before_global_schur",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 0,
                    "lifecycle_state": "local q product/lift/carrier owners released",
                    **lifecycle_facts,
                },
            )
        condensed = _static_condense_augmented_q(
            diagonal_q_augmented,
            entities,
            len(q_modes),
            allocation_gate=allocation_gate,
            q=q,
        )
        if allocation_gate is not None:
            allocation_gate(
                "task40_v18_independent_global_schur_complete",
                {
                    "additional_payload_bytes": 0,
                    "workspace_bytes": 0,
                    "q": q,
                    "lifecycle_state": "global Schur returned; diagonal q owner still live",
                    "diagonal_q_augmented_csr_payload_bytes": owner_payloads[
                        "diagonal_q_augmented_csr_payload_bytes"
                    ],
                    "condensed_schur_csr_payload_bytes": _csr_payload_bytes(condensed),
                },
            )
        del diagonal_q_augmented
        candidate = candidates[q]
        if condensed.shape != candidate.shape:
            raise ValueError(
                f"q={q} independent Schur shape {condensed.shape} differs from candidate {candidate.shape}"
            )
        difference_nnz_upper = int(condensed.nnz + candidate.nnz)
        if allocation_gate is not None:
            allocation_gate(
                "task40_v18_independent_candidate_schur_difference",
                {
                    "additional_payload_bytes": int(
                        difference_nnz_upper * 20
                        + (condensed.shape[0] + 1) * 4
                    ),
                    "workspace_bytes": int(difference_nnz_upper * 16),
                    "q": q,
                    "independent_schur_nnz": int(condensed.nnz),
                    "candidate_schur_nnz": int(candidate.nnz),
                    "difference_nnz_upper": difference_nnz_upper,
                },
            )
        difference = (condensed - candidate).tocsr()
        schur_norm = _frobenius(condensed)
        candidate_norm = _frobenius(candidate)
        difference_norm = _frobenius(difference)
        relative = difference_norm / max(
            schur_norm, candidate_norm, np.finfo(float).tiny
        )
        schur_errors[q] = relative
        schur_norms[q] = {
            "independent_schur_frobenius": schur_norm,
            "candidate_csr_frobenius": candidate_norm,
            "complete_difference_frobenius": difference_norm,
        }
        del difference, condensed, candidate
    if full_q_block_coverage != ny2 or set(diagonal_norms) != set(range(ny)):
        raise ValueError("complete ordered q-block coverage omitted one or more FE/port blocks")
    diagonal_scale = max(max(diagonal_norms.values()), np.finfo(float).tiny)
    offdiagonal_norms = {
        f"{p}{q}": float(np.sqrt(value))
        for (p, q), value in offdiagonal_squared.items()
    }
    offdiagonal_relative = {
        key: value / diagonal_scale for key, value in offdiagonal_norms.items()
    }
    maximum_offdiagonal_relative = max(offdiagonal_relative.values(), default=0.0)
    maximum_schur_relative = max(schur_errors.values(), default=float("inf"))
    mapping_defect = float(
        np.linalg.norm(layout.cell_dft.conj().T @ layout.cell_dft - np.eye(ny))
    )
    phase_defect = float(abs(complex(layout.phase_y) - 1.0))
    empty_qs = [q for q, count in enumerate(q_port_counts) if count == 0]
    q4_nonzero_fe_rhs = (
        bool(q4_rhs_norm is not None and np.isfinite(q4_rhs_norm) and q4_rhs_norm > 0.0)
    )
    nonhermitian_witness = max(nonhermitian_relative.values(), default=0.0) > 1.0e-12
    volume_imaginary_nnz = _imaginary_nonzero_count(volume.data)
    complex_material_witness = volume_imaginary_nnz > 0
    q4_empty_port_gate = (
        ny != 8
        or (
            expected_q_port_counts[4] == 0
            and not len(mode_indices_by_q[4])
            and q4_nonzero_fe_rhs
        )
    )
    passed = bool(
        maximum_offdiagonal_relative <= tolerance
        and maximum_schur_relative <= tolerance
        and mapping_defect <= MAPPING_LIMIT
        and phase_defect > MAPPING_LIMIT
        and q4_empty_port_gate
        and nonhermitian_witness
        and complex_material_witness
    )
    return {
        "schema": "task40extra.review_v18_complete_ny_reference_operator.v1",
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "oracle": "independent full native MPC volume assembly + original C/D/H carrier + complete q congruence + independent global sparse Schur solve",
        "candidate": "local two-cell native cell-tensor condensation and preallocated/row-tile q assembly",
        "ny": ny,
        "translation_count_K": ny // 2,
        "local_y_cells_ell": 2,
        "native_independent_rows": native_rows,
        "full_q_block_coverage_count": full_q_block_coverage,
        "expected_full_q_block_coverage_count": ny2,
        "all_ordered_q_blocks_covered": full_q_block_coverage == ny2,
        "q_port_counts": q_port_counts,
        "empty_port_q_indices": empty_qs,
        "q4_fe_basis_rows": int(width) if 4 in range(ny) else None,
        "q4_nonzero_fe_rhs_norm": q4_rhs_norm,
        "q4_nonzero_fe_rhs_witness_passed": q4_nonzero_fe_rhs,
        "q4_zero_port_nonzero_fe_gate_passed": q4_empty_port_gate,
        "mode_identities_covered_once": bool(mode_count == sum(q_port_counts)),
        "complex_nonhermitian_reference_witness_relative": max(nonhermitian_relative.values(), default=0.0),
        "complex_nonhermitian_reference_witness_passed": nonhermitian_witness,
        "complex_material_volume_imaginary_nnz": volume_imaginary_nnz,
        "complex_material_volume_witness_passed": complex_material_witness,
        "original_H_mode_count": int(len(h_values)),
        "original_H_minimum": float(np.min(h_values)) if len(h_values) else None,
        "original_H_maximum": float(np.max(h_values)) if len(h_values) else None,
        "global_y_phase": [complex(layout.phase_y).real, complex(layout.phase_y).imag],
        "global_y_phase_distance_from_one": phase_defect,
        "mapping_limit": MAPPING_LIMIT,
        "operator_limit": tolerance,
        "q_dft_unitarity_frobenius_defect": mapping_defect,
        "q_dft_mapping_passed": mapping_defect <= MAPPING_LIMIT,
        "offdiagonal_diagonal_frobenius_scale": diagonal_scale,
        "complete_augmented_diagonal_frobenius_by_q": {
            str(q): diagonal_norms[q] for q in range(ny)
        },
        "offdiagonal_frobenius_by_block": offdiagonal_norms,
        "offdiagonal_relative_by_block": offdiagonal_relative,
        "maximum_complete_offdiagonal_relative": maximum_offdiagonal_relative,
        "independent_schur_relative_by_q": schur_errors,
        "independent_schur_norms_by_q": schur_norms,
        "maximum_independent_schur_relative": maximum_schur_relative,
        "complete_q_block_shapes": block_shapes,
        "independent_full_volume_nnz": int(volume.nnz),
        "independent_carrier_C_nnz": int(coupling.nnz),
        "independent_carrier_D_nnz": int(projection.nnz),
        "candidate_q_matrix_nnz": {
            str(q): int(candidates[q].nnz) for q in range(ny)
        },
        "contributions": ["full native FE volume", "left C/sqrt(H)", "right D/sqrt(H)", "-I port normalization"],
    }


def _mpc_cell_pattern_support_upper(space: Any, mpc: Any) -> dict[str, int]:
    """Bound MPC matrix support as raw cell dofs plus appended master dofs.

    DOLFINx-MPC keeps the original cell dofs in its sparsity pattern and adds
    master dofs for constrained rows and columns.  This is a storage pattern,
    not the smaller mathematical support obtained by replacing each slave.
    The temporary support buffer is limited to one owned cell at a time.
    """
    slaves = np.asarray(mpc.slaves, dtype=np.int64).reshape(-1)
    master_count_by_slave: dict[int, int] = {}
    maximum_slave_master_count = 0
    for slave in slaves:
        masters = np.asarray(mpc.masters.links(int(slave)), dtype=np.int64).reshape(-1)
        if masters.size == 0:
            raise ValueError("finalized Floquet MPC contains a slave without master support")
        master_count_by_slave[int(slave)] = len(masters)
        maximum_slave_master_count = max(maximum_slave_master_count, len(masters))

    cell_count = int(space.mesh.topology.index_map(3).size_local)
    max_support_buffer_entries = 0
    for cell in range(cell_count):
        dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int64).reshape(-1)
        appended_master_count = sum(
            master_count_by_slave.get(int(dof), 0) for dof in dofs
        )
        max_support_buffer_entries = max(
            max_support_buffer_entries, len(dofs) + appended_master_count
        )

    support_buffer = np.empty(max_support_buffer_entries, dtype=np.int64)
    raw_support_pairs = 0
    constraint_replaced_support_pairs = 0
    backend_union_support_pairs = 0
    raw_cell_dof_sum = 0
    constraint_replaced_cell_dof_sum = 0
    backend_union_cell_dof_sum = 0
    maximum_raw_cell_dof_count = 0
    maximum_constraint_replaced_cell_dof_count = 0
    maximum_backend_union_cell_dof_count = 0
    for cell in range(cell_count):
        dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int64).reshape(-1)
        raw_count = len(dofs)
        support_buffer[:raw_count] = dofs
        cursor = raw_count
        constraint_replaced_count = 0
        for dof in dofs:
            master_count = master_count_by_slave.get(int(dof), 0)
            if master_count == 0:
                constraint_replaced_count += 1
                continue
            masters = np.asarray(
                mpc.masters.links(int(dof)), dtype=np.int64
            ).reshape(-1)
            if len(masters) != master_count:
                raise ValueError("finalized MPC master support changed during counting")
            constraint_replaced_count += master_count
            next_cursor = cursor + master_count
            support_buffer[cursor:next_cursor] = masters
            cursor = next_cursor

        backend_support = support_buffer[:cursor]
        backend_support.sort()
        backend_union_count = 1 + int(
            np.count_nonzero(backend_support[1:] != backend_support[:-1])
        ) if cursor else 0

        raw_support_pairs += raw_count * raw_count
        constraint_replaced_support_pairs += (
            constraint_replaced_count * constraint_replaced_count
        )
        backend_union_support_pairs += backend_union_count * backend_union_count
        raw_cell_dof_sum += raw_count
        constraint_replaced_cell_dof_sum += constraint_replaced_count
        backend_union_cell_dof_sum += backend_union_count
        maximum_raw_cell_dof_count = max(maximum_raw_cell_dof_count, raw_count)
        maximum_constraint_replaced_cell_dof_count = max(
            maximum_constraint_replaced_cell_dof_count,
            constraint_replaced_count,
        )
        maximum_backend_union_cell_dof_count = max(
            maximum_backend_union_cell_dof_count, backend_union_count
        )

    return {
        "owned_cell_count": cell_count,
        "slave_dof_count": len(slaves),
        "raw_cell_support_pairs_sum": raw_support_pairs,
        "constraint_replaced_cell_support_pairs_sum": (
            constraint_replaced_support_pairs
        ),
        "backend_raw_plus_masters_union_pairs_sum": backend_union_support_pairs,
        "raw_cell_dof_sum": raw_cell_dof_sum,
        "constraint_replaced_cell_dof_sum": constraint_replaced_cell_dof_sum,
        "backend_union_cell_dof_sum": backend_union_cell_dof_sum,
        "maximum_raw_cell_dof_count": maximum_raw_cell_dof_count,
        "maximum_constraint_replaced_cell_dof_count": (
            maximum_constraint_replaced_cell_dof_count
        ),
        "maximum_backend_union_cell_dof_count": (
            maximum_backend_union_cell_dof_count
        ),
        "support_count_workspace_upper_bytes": int(
            support_buffer.nbytes
            + maximum_slave_master_count * np.dtype(np.int64).itemsize
        ),
    }


def assemble_and_qualify_complete_ny_reference_operator(
    *,
    bundle: Mapping[str, Any],
    entities: Any,
    layout: Any,
    sectors: Sequence[Any],
    candidate_q_matrices: Mapping[int, Any],
    expected_q_port_counts: Sequence[int],
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    """Independently assemble the full native FE volume, then qualify every q block."""
    from dolfinx import fem
    import dolfinx_mpc
    from petsc4py import PETSc

    setup = bundle["setup"]
    degree = int(bundle["degree"])
    space = setup["spaces"][degree]
    floquet = setup["floquets"][degree]
    if getattr(floquet, "mpc", None) is None:
        raise ValueError("complete reference oracle requires the actual finalized FE MPC")
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    compiled = fem.form(
        bundle["volume_action"].bilinear_form,
        jit_options=dict(SAME_MESH_JIT_OPTIONS),
    )
    storage_rows = int(space.dofmap.index_map.size_local)
    independent = np.asarray(entities.independent, dtype=np.int64)
    int32_limit = int(np.iinfo(np.int32).max)
    if (
        storage_rows != int(entities.full_rows)
        or storage_rows > int32_limit
        or len(independent) > int32_limit
    ):
        raise OverflowError("full native FE storage shape exceeds the qualified PetscInt range")
    mpc = floquet.mpc
    support = _mpc_cell_pattern_support_upper(space, mpc)
    mathematical_constraint_nnz_upper = int(
        storage_rows + support["constraint_replaced_cell_support_pairs_sum"]
    )
    structural_nnz_upper = int(
        storage_rows + support["backend_raw_plus_masters_union_pairs_sum"]
    )
    if structural_nnz_upper > int32_limit:
        raise OverflowError("preassembly full FE structural NNZ upper bound exceeds PetscInt range")
    index_bytes = np.dtype(PETSc.IntType).itemsize
    scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
    csr_payload_upper = int(
        (storage_rows + 1) * index_bytes
        + structural_nnz_upper * (index_bytes + scalar_bytes)
    )
    allocation_gate(
        "task40_v18_full_native_volume_matrix_preallocation_admission",
        {
            "additional_payload_bytes": int(csr_payload_upper),
            "workspace_bytes": int(
                csr_payload_upper + support["support_count_workspace_upper_bytes"]
            ),
            "backend_pattern_nnz_upper_from_raw_cell_and_MPC_master_union": (
                structural_nnz_upper
            ),
            "legacy_constraint_replaced_nnz_upper": (
                mathematical_constraint_nnz_upper
            ),
            "structural_nnz_upper_from_actual_cell_MPC_support": structural_nnz_upper,
            **support,
            "full_storage_rows": storage_rows,
            "matrix_payload_upper_bytes": csr_payload_upper,
            "support_bound_semantics": (
                "per-owned-cell union of original cell dofs and appended MPC masters"
            ),
            "independent_oracle": "full_native_dolfinx_mpc_matrix_then_compact_independent_rows",
            "preallocation_admitted_before_create_matrix": True,
        },
    )
    matrix = None
    try:
        matrix = dolfinx_mpc.cpp.mpc.create_matrix(
            compiled._cpp_object, floquet.mpc._cpp_object, floquet.mpc._cpp_object
        )
        preallocation = matrix.getInfo()
        allocated_nnz = int(preallocation.get("nz_allocated", 0))
        matrix_shape = tuple(map(int, matrix.getSize()))
        actual_payload_bytes = int(
            (storage_rows + 1) * index_bytes
            + allocated_nnz * (index_bytes + scalar_bytes)
        )
        allocation_gate(
            "task40_v18_full_native_volume_matrix_preassembly_actual_inventory",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 0,
                "allocated_nnz": allocated_nnz,
                "allocated_structural_nnz": allocated_nnz,
                "nz_used_before_assembly": int(preallocation.get("nz_used", 0)),
                "admitted_backend_pattern_nnz_upper": structural_nnz_upper,
                "legacy_constraint_replaced_nnz_upper": (
                    mathematical_constraint_nnz_upper
                ),
                "raw_cell_support_pairs_sum": support[
                    "raw_cell_support_pairs_sum"
                ],
                "constraint_replaced_cell_support_pairs_sum": support[
                    "constraint_replaced_cell_support_pairs_sum"
                ],
                "backend_raw_plus_masters_union_pairs_sum": support[
                    "backend_raw_plus_masters_union_pairs_sum"
                ],
                "matrix_shape": list(matrix_shape),
                "full_storage_rows": storage_rows,
                "matrix_payload_bytes": actual_payload_bytes,
                "preallocation_within_admitted_upper": (
                    allocated_nnz <= structural_nnz_upper
                ),
                "independent_oracle": "full_native_dolfinx_mpc_matrix_then_compact_independent_rows",
            },
        )
        if matrix_shape != (storage_rows, storage_rows):
            raise ValueError(
                "preallocated full FE matrix has unexpected storage dimensions; "
                f"actual_allocated_nnz={allocated_nnz}, "
                f"backend_pattern_nnz_upper={structural_nnz_upper}, "
                f"legacy_constraint_replaced_nnz_upper={mathematical_constraint_nnz_upper}"
            )
        if allocated_nnz > structural_nnz_upper:
            raise MemoryError(
                "actual PETSc preallocation exceeds the admitted raw-cell/MPC-master "
                f"union upper bound: allocated_nnz={allocated_nnz}, "
                f"backend_union_nnz_upper={structural_nnz_upper}, "
                f"legacy_constraint_replaced_nnz_upper={mathematical_constraint_nnz_upper}, "
                f"raw_cell_support_pairs_sum={support['raw_cell_support_pairs_sum']}, "
                "constraint_replaced_cell_support_pairs_sum="
                f"{support['constraint_replaced_cell_support_pairs_sum']}, "
                "backend_raw_plus_masters_union_pairs_sum="
                f"{support['backend_raw_plus_masters_union_pairs_sum']}"
            )
        dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, bcs=[], A=matrix)
        matrix.assemble()
        postassembly = matrix.getInfo()
        used_nnz = int(postassembly.get("nz_used", allocated_nnz))
        allocation_gate(
            "task40_v18_full_native_volume_matrix_postassembly_actual_inventory",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": 0,
                "allocated_nnz": allocated_nnz,
                "used_nnz": used_nnz,
                "admitted_backend_pattern_nnz_upper": structural_nnz_upper,
                "legacy_constraint_replaced_nnz_upper": (
                    mathematical_constraint_nnz_upper
                ),
                "raw_cell_support_pairs_sum": support[
                    "raw_cell_support_pairs_sum"
                ],
                "constraint_replaced_cell_support_pairs_sum": support[
                    "constraint_replaced_cell_support_pairs_sum"
                ],
                "backend_raw_plus_masters_union_pairs_sum": support[
                    "backend_raw_plus_masters_union_pairs_sum"
                ],
                "matrix_shape": list(matrix_shape),
                "full_storage_rows": storage_rows,
                "matrix_payload_bytes": int(
                    (storage_rows + 1) * index_bytes
                    + used_nnz * (index_bytes + scalar_bytes)
                ),
                "used_within_allocated_and_integer_range": (
                    used_nnz <= allocated_nnz and used_nnz <= int32_limit
                ),
                "independent_oracle": "full_native_dolfinx_mpc_matrix_then_compact_independent_rows",
            },
        )
        if used_nnz > allocated_nnz or used_nnz > int32_limit:
            raise OverflowError("assembled native FE CSR NNZ exceeds its admitted PetscInt inventory")
        full_csr_payload = int(
            (storage_rows + 1) * index_bytes + used_nnz * (index_bytes + scalar_bytes)
        )
        compact_csr_upper = int(
            (len(independent) + 1) * index_bytes
            + used_nnz * (index_bytes + scalar_bytes)
        )
        allocation_gate(
            "task40_v18_native_CSR_copy_and_compaction_admission",
            {
                "additional_payload_bytes": int(
                    full_csr_payload
                    + compact_csr_upper
                    + storage_rows * index_bytes
                    + len(independent) * (2 * index_bytes + np.dtype(np.int64).itemsize)
                ),
                "workspace_bytes": int(used_nnz * (np.dtype(np.int64).itemsize + 1)),
                "full_native_CSR_copy_upper_bytes": full_csr_payload,
                "independent_compact_CSR_upper_bytes": compact_csr_upper,
                "compact_row_map_bytes": storage_rows * index_bytes,
                "independent_row_count_bytes": len(independent)
                * (2 * index_bytes + np.dtype(np.int64).itemsize),
                "native_CSR_workspace_upper_bytes": int(
                    used_nnz * (np.dtype(np.int64).itemsize + 1)
                ),
                "matrix_still_live_during_independent_copy": True,
            },
        )
        native_indptr, native_indices, native_data = matrix.getValuesCSR()
        native_indptr = np.asarray(native_indptr)
        native_indices = np.asarray(native_indices)
        native_data = np.asarray(native_data)
        if (
            native_indptr.shape != (storage_rows + 1,)
            or native_indices.ndim != 1
            or native_data.shape != native_indices.shape
            or len(native_indices) != used_nnz
            or not np.issubdtype(native_indptr.dtype, np.signedinteger)
            or not np.issubdtype(native_indices.dtype, np.signedinteger)
            or int(native_indptr[0]) != 0
            or int(native_indptr[-1]) != used_nnz
            or np.any(native_indptr[1:] < native_indptr[:-1])
            or (native_indices.size and (
                int(native_indices.min()) < 0
                or int(native_indices.max()) >= storage_rows
                or int(native_indices.max()) > int32_limit
            ))
            or not np.isfinite(native_data).all()
        ):
            raise ValueError("independent full FE matrix CSR storage is incomplete or non-finite")
        indptr = _owned_array_or_copy(native_indptr, dtype=np.int32)
        indices = _owned_array_or_copy(native_indices, dtype=np.int32)
        data = _owned_array_or_copy(native_data, dtype=np.complex128)
        del native_indptr, native_indices, native_data
        if len(independent) and (
            int(independent.min()) < 0 or int(independent.max()) >= storage_rows
        ):
            raise ValueError("independent FE rows lie outside the full storage index range")
        compact_map = np.full(storage_rows, -1, dtype=np.int32)
        compact_map[independent] = np.arange(len(independent), dtype=np.int32)
        row_nnz = np.empty(len(independent), dtype=np.int64)
        for compact_row, full_row in enumerate(independent):
            start, stop = int(indptr[full_row]), int(indptr[full_row + 1])
            mapped = compact_map[indices[start:stop]]
            row_nnz[compact_row] = int(np.count_nonzero(mapped >= 0))
        compact_row_ptr = np.cumsum(row_nnz, dtype=np.int64)
        if len(compact_row_ptr) and int(compact_row_ptr[-1]) > np.iinfo(np.int32).max:
            raise OverflowError("independent full native volume exceeds the qualified PetscInt CSR range")
        compact_indptr = np.empty(len(independent) + 1, dtype=np.int32)
        compact_indptr[0] = 0
        compact_indptr[1:] = compact_row_ptr
        compact_nnz = int(compact_indptr[-1])
        compact_indices = np.empty(compact_nnz, dtype=np.int32)
        compact_data = np.empty(compact_nnz, dtype=np.complex128)
        cursor = 0
        for compact_row, full_row in enumerate(independent):
            start, stop = int(indptr[full_row]), int(indptr[full_row + 1])
            mapped = compact_map[indices[start:stop]]
            keep = mapped >= 0
            count = int(np.count_nonzero(keep))
            end = cursor + count
            compact_indices[cursor:end] = mapped[keep]
            compact_data[cursor:end] = data[start:stop][keep]
            cursor = end
        if cursor != compact_nnz:
            raise RuntimeError("independent row compaction count changed during copy")
        volume = sparse.csr_matrix(
            (compact_data, compact_indices, compact_indptr),
            shape=(len(independent), len(independent)),
            copy=False,
        )
        if not volume.has_canonical_format or not np.isfinite(volume.data).all():
            raise ValueError("independent full native volume CSR is not canonical complex128")
        matrix.destroy()
        matrix = None
        del indptr, indices, data, compact_map, row_nnz, compact_row_ptr
        facts = qualify_complete_ny_reference_operator(
            volume_matrix=volume,
            entities=entities,
            layout=layout,
            carrier=bundle["dtn_action"].carrier,
            sectors=sectors,
            candidate_q_matrices=candidate_q_matrices,
            expected_q_port_counts=expected_q_port_counts,
            allocation_gate=allocation_gate,
        )
        facts.update({
            "full_volume_matrix_shape": list(volume.shape),
            "full_volume_matrix_structural_nnz": int(volume.nnz),
            "full_volume_pattern_allocated_nnz": allocated_nnz,
            "full_volume_pattern_used_nnz": used_nnz,
            "full_volume_pattern_structural_nnz_upper": structural_nnz_upper,
            "full_volume_csr_payload_bytes": int(volume.data.nbytes + volume.indices.nbytes + volume.indptr.nbytes),
            "full_volume_row_count_including_mpc_slaves": int(storage_rows),
            "full_volume_compacted_to_independent_rows": int(len(independent)),
            "full_volume_matrix_assembly": "dolfinx_mpc.assemble_matrix on full actual p6 reference space",
            "full_native_petsc_matrix_released_before_q_oracle": True,
        })
        return facts
    finally:
        if matrix is not None:
            matrix.destroy()
