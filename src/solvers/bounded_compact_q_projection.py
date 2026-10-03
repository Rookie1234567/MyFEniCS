"""Opt-in exact compact q projection with a named-NumPy-array byte budget.

The budget covers the accumulator CSR and all explicitly allocated projection,
merge and validation arrays. It is NOT a process/RSS cap: q maps, contribution
producers/recipes, Python objects and internal NumPy/SciPy/native packing and
workspace remain outside it and require the caller's fresh process-tree gate.
Dense q maps and projected output are admitted tiles, never unbounded
support-wide copies. No COO or sparse-addition workspace is created. The final
CSR cannot be made arbitrarily small: each replacement is counted exactly and
admitted before allocating its buffers.

This is a memory-first research path. Repeated scalar CSR merges can be slower
than the legacy whole-support GEMMs. No accuracy/production/speedup claim follows
from the small algebra tests. All entries are retained except exact zeros.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse

from .original_port_blocks import (
    CachedPortCorrection, DenseOriginalPortBlock, DiagonalOriginalPortBlock,
)
from .y_orbit_sparse_reference import integer_admission


def _bytes(matrix):
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _positive_integer(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(name + ' must be a positive Python integer')
    return value


def _gather_tile(matrix, rows, first, last):
    """Gather only one dense column tile, accumulating repeated CSR indices.

    No row slice, CSC conversion, support array, advanced-indexing temporary or
    conjugate copy is needed. Repeated native rows remain separate rows, as in
    literal matrix[rows, :]. The provider independently validates its stricter
    native-contribution uniqueness contract.
    """
    out = np.zeros((len(rows), last - first), dtype=np.complex128)
    for i, row in enumerate(rows):
        begin, end = int(matrix.indptr[int(row)]), int(matrix.indptr[int(row) + 1])
        for k in range(begin, end):
            column = int(matrix.indices[k])
            if first <= column < last:
                out[i, column - first] += matrix.data[k]
    return out


def _shift_indptr(source, delta, target):
    """Compute in int64 even across CSR int32/int64 promotion or demotion."""
    np.add(source, delta, out=target, dtype=np.int64)


def _merged_entries(old, tile, row_first, col_first):
    """Exact union for the affected rows, with constant-size scalar scratch."""
    row_last, col_last = row_first + tile.shape[0], col_first + tile.shape[1]
    for row in range(row_first, row_last):
        begin, end = int(old.indptr[row]), int(old.indptr[row + 1])
        k = begin
        for column in range(col_first, col_last):
            while k < end and int(old.indices[k]) < column:
                if old.data[k] != 0:
                    yield row, int(old.indices[k]), old.data[k]
                k += 1
            value = tile[row - row_first, column - col_first]
            if k < end and int(old.indices[k]) == column:
                value = old.data[k] + value
                k += 1
            if not np.isfinite(value):
                raise FloatingPointError('compact q accumulation produced a nonfinite entry')
            if value != 0:
                yield row, column, value
        for k in range(k, end):
            if old.data[k] != 0:
                yield row, int(old.indices[k]), old.data[k]


class BoundedCompactQAccumulator:
    """Own only a growing exact CSR; borrow maps, indices and numeric recipes.

    ``max_owned_bytes`` includes old/new CSR coexistence, not just returned
    storage. NumPy/SciPy/native workspace is explicitly unknown, not a fake bound.
    ``tile_width`` is an upper bound; panels shrink before each unprocessed
    tile when necessary. Insufficient minimum scratch or final CSR capacity
    raises before that allocation.
    """

    def __init__(self, shape, *, max_owned_bytes, tile_width, index_dtype, gate):
        self.budget = _positive_integer(max_owned_bytes, 'max_owned_bytes')
        self.tile_width = _positive_integer(tile_width, 'tile_width')
        if not callable(gate):
            raise ValueError('a fresh aggregate allocation gate is required')
        self.shape = tuple(map(int, shape))
        self.index_dtype = np.dtype(index_dtype)
        self.ibytes = max(8, self.index_dtype.itemsize, np.dtype(np.intp).itemsize)
        integer_admission(self.shape, 0, index_dtype=self.index_dtype)
        self.gate = gate
        self.result = None
        self.peak_owned_upper_bytes = 0
        self.tiles_projected = 0
        self._admit('empty_result', (self.shape[0] + 1) * self.ibytes)
        self.result = sparse.csr_matrix(self.shape, dtype=np.complex128)

    def _admit(self, label, additional, **facts):
        resident = 0 if self.result is None else _bytes(self.result)
        upper = resident + int(additional)
        if upper > self.budget:
            reason = ('minimum projection scratch cannot fit with the current CSR'
                      if label.startswith('projection/') else
                      'complete final CSR/merge storage for this exact plan cannot fit; '
                      'it cannot be omitted or truncated')
            raise MemoryError(
                f'compact q named-array budget exceeded before {label}: '
                f'current CSR {resident} + additional {int(additional)} = {upper} '
                f'> {self.budget} bytes; {reason} '
                '(NumPy/SciPy/native workspace is separate)')
        self.gate('bounded/' + label, payload=int(additional),
                  bounded_current_result_bytes=resident,
                  projection_owned_upper_bytes=upper,
                  projection_owned_budget_bytes=self.budget,
                  projection_owned_budget_includes_current_result=True,
                  projection_owned_budget_excludes_borrowed_maps_and_recipes=True,
                  projection_owned_budget_excludes_Python_and_native_workspace=True,
                  no_COO_or_sparse_addition_workspace=True, **facts)
        self.peak_owned_upper_bytes = max(self.peak_owned_upper_bytes, upper)

    @staticmethod
    def _scratch(rows, cols, values, a, b):
        if isinstance(values, CachedPortCorrection):
            inner = int(values.XiB.shape[0])
            factors = a * inner + inner * b
        elif isinstance(values, DiagonalOriginalPortBlock):
            factors = 0  # scale the owned right tile in place
        else:
            factors = a * len(cols)
        return 16 * (len(rows) * a + len(cols) * b + factors + a * b)

    def add(self, left, right, rows, cols, values, label):
        """Add Qp[rows]^H values Qq[cols], or its exact borrowed-factor recipe.

        All provider payload validation precedes this call. This helper never
        retains inputs; the producer may release its recipe on iterator advance.
        """
        if not len(rows) or not len(cols) or not min(self.shape):
            return
        width = min(self.tile_width, max(self.shape))
        # Account for both maps, conjugation in place, every GEMM output and
        # projected tile simultaneously. Native BLAS packing is not included.
        while width > 1 and (_bytes(self.result) + self._scratch(
                rows, cols, values, min(width, self.shape[0]), min(width, self.shape[1])) > self.budget):
            width = max(1, width // 2)
        for first_p in range(0, self.shape[0], width):
            last_p = min(first_p + width, self.shape[0])
            for first_q in range(0, self.shape[1], width):
                last_q = min(first_q + width, self.shape[1])
                self._project_tile(left, right, rows, cols, values, label,
                                   first_p, last_p, first_q, last_q)

    def _project_tile(self, left, right, rows, cols, values, label,
                      first_p, last_p, first_q, last_q):
        a, b = last_p - first_p, last_q - first_q
        scratch = self._scratch(rows, cols, values, a, b)
        if _bytes(self.result) + scratch > self.budget and max(a, b) > 1:
            # Recheck after each prior tile: a growing exact result must not
            # cause a false rejection when a smaller unprocessed tile fits.
            self._split_tile(left, right, rows, cols, values, label,
                             first_p, last_p, first_q, last_q)
            return
        self._admit('projection/' + str(label), scratch,
                    tile_rows=a, tile_columns=b,
                    full_output_shape=list(self.shape),
                    borrowed_correction_factors=isinstance(values, CachedPortCorrection))
        l = _gather_tile(left, rows, first_p, last_p)
        if not np.count_nonzero(l):
            del l
            return
        r = _gather_tile(right, cols, first_q, last_q)
        if not np.count_nonzero(r):
            del l, r
            return
        np.conjugate(l, out=l)  # Q^H, never inverse/transpose-only
        if isinstance(values, CachedPortCorrection):
            dual = l.T @ values.Di
            primal = values.XiB @ r
            projected = dual @ primal
            del dual, primal
        elif isinstance(values, DiagonalOriginalPortBlock):
            for row, diagonal in enumerate(values.diagonal):
                r[row, :] *= diagonal
            projected = l.T @ r
        else:
            matrix = values.numeric_arrays[0] if isinstance(values, DenseOriginalPortBlock) else values
            dual = l.T @ matrix
            projected = dual @ r
            del dual, matrix
        del l, r
        # Scalar checks avoid an unaccounted full-size finite mask.
        if any(not np.isfinite(value) for value in projected.flat):
            raise FloatingPointError('compact projected contribution is nonfinite: ' + str(label))
        self.tiles_projected += 1
        missing = None
        if np.count_nonzero(projected):
            missing = self._merge(projected, first_p, first_q, label)
        del projected  # release full backing before any smaller-tile retry
        if missing is not None:
            if max(a, b) > 1:
                self._split_tile(left, right, rows, cols, values, label,
                                 first_p, last_p, first_q, last_q)
            else:
                self._admit('CSR_merge/' + str(label), missing)

    def _split_tile(self, left, right, rows, cols, values, label,
                    first_p, last_p, first_q, last_q):
        a, b = last_p - first_p, last_q - first_q
        if a >= b and a > 1:
            middle = first_p + a // 2
            tiles = ((first_p, middle, first_q, last_q),
                     (middle, last_p, first_q, last_q))
        else:
            middle = first_q + b // 2
            tiles = ((first_p, last_p, first_q, middle),
                     (first_p, last_p, middle, last_q))
        for bounds in tiles:
            self._project_tile(left, right, rows, cols, values, label, *bounds)

    def _merge(self, tile, first_p, first_q, label):
        old = self.result
        # First pass counts the actual exact union/cancellations. No index or
        # numeric arrays are allocated until the complete replacement fits.
        last_p = first_p + tile.shape[0]
        first_old, last_old = int(old.indptr[first_p]), int(old.indptr[last_p])
        local_count = sum(1 for _ in _merged_entries(old, tile, first_p, first_q))
        count = int(old.nnz) - (last_old - first_old) + local_count
        integer_admission(self.shape, count, index_dtype=self.index_dtype)
        integer_admission(self.shape, count, index_dtype=np.intp)
        dtype = np.dtype(np.int32 if max(*self.shape, count) <= np.iinfo(np.int32).max else np.int64)
        new_bytes = count * (16 + dtype.itemsize) + (self.shape[0] + 1) * dtype.itemsize
        # Covers input CSR buffers plus a complete possible constructor copy.
        # SciPy ordinarily shares them, but zero-copy is not assumed for budget.
        additional = tile.nbytes + 2 * new_bytes
        if _bytes(old) + additional > self.budget:
            # Caller releases this projected buffer before recomputing smaller
            # tiles. No exception traceback can retain the old large tile.
            return additional
        self._admit('CSR_merge/' + str(label), additional,
                    exact_next_CSR_entries=count, next_CSR_payload_bytes=new_bytes,
                    projected_tile_bytes=int(tile.nbytes),
                    fresh_RSS_allowance_conservatively_recounts_current_tile=True,
                    CSR_constructor_copy_allowance_bytes=new_bytes)
        data = np.empty(count, dtype=np.complex128)
        indices = np.empty(count, dtype=dtype)
        indptr = np.zeros(self.shape[0] + 1, dtype=dtype)
        # Bulk-copy unaffected prefixes/suffixes as views, not scalar Python
        # merges over the entire accumulated matrix for every output tile.
        data[:first_old], indices[:first_old] = old.data[:first_old], old.indices[:first_old]
        end_new = first_old + local_count
        data[end_new:], indices[end_new:] = old.data[last_old:], old.indices[last_old:]
        indptr[:first_p + 1] = old.indptr[:first_p + 1]
        for offset, (row, column, value) in enumerate(
                _merged_entries(old, tile, first_p, first_q), start=first_old):
            data[offset], indices[offset] = value, column
            indptr[row + 1] += 1
        np.cumsum(indptr[first_p:last_p + 1], out=indptr[first_p:last_p + 1])
        _shift_indptr(old.indptr[last_p + 1:], local_count - (last_old - first_old),
                      indptr[last_p + 1:])
        self.result = sparse.csr_matrix((data, indices, indptr), shape=self.shape, copy=False)

    def finish(self):
        """Validate canonical CSR without vector-sized temporary masks."""
        audit_csr_scalar(self.result, index_dtype=self.index_dtype)
        self._admit('complete', 0, exact_final_CSR_bytes=_bytes(self.result),
                    tiles_projected=self.tiles_projected)
        return self.result


def audit_csr_scalar(result, *, index_dtype):
    """Validate canonical finite complex128 CSR without ndarray-sized scratch."""
    if not sparse.isspmatrix_csr(result) or result.dtype != np.dtype(np.complex128):
        raise ValueError('require an existing complex128 CSR; no implicit copy')
    integer_admission(result.shape, result.nnz, index_dtype=index_dtype)
    integer_admission(result.shape, result.nnz, index_dtype=result.indices.dtype,
                      indptr_dtype=result.indptr.dtype)
    previous = 0
    for row in range(result.shape[0]):
        end = int(result.indptr[row + 1])
        if not previous <= end <= result.nnz:
            raise ValueError('invalid bounded compact CSR pointer')
        last_column = -1
        for k in range(previous, end):
            column = int(result.indices[k])
            if not last_column < column < result.shape[1] or not np.isfinite(result.data[k]):
                raise ValueError('invalid bounded compact CSR entry')
            last_column = column
        previous = end
    if int(result.indptr[0]) != 0 or previous != result.nnz:
        raise ValueError('incomplete bounded compact CSR')
