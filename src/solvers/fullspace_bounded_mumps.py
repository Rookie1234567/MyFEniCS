"""Explicitly bounded development p1 factors with symbolic-before-numeric gates."""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

import numpy as np

from .fullspace_physical_intermediate import LOCAL_FACTOR_MAX_BYTES, LOCAL_FACTOR_MAX_ROWS
from .fullspace_v17_p3_oracle import _MumpsFactor


class BoundedP1Factor:
    """Borrow one p1 matrix, own one MUMPS factor, expose the existing solve_lean API.

    MUMPS INFOG17/19/22 are respectively estimated, allocated and used internal
    memory sums in decimal MB (MUMPS user guide). Values are rounded, so budgets
    use the next MB as an upper bound. Matrix CSR payload is reported separately
    from PETSc's allocator report and from the whole-job process-tree RSS.
    """

    def __init__(self, matrix: Any, *, label: str, resource_sample: Callable[[], dict],
                 marker: Callable[[str, dict], None], physical_p2_pilot: bool = False, extra_local_bytes: int = 0) -> None:
        self.matrix, self.label = matrix, label
        self.factor = None
        self.solve_count = 0
        self.last_apply_facts: dict = {}
        self.audit: dict = {'label': label, 'bounded_development_coarse_factor': True}
        emit = lambda name, facts: marker(name.replace('p1_', 'p2_') if physical_p2_pilot else name, facts)
        row_cap = 8192 if physical_p2_pilot else LOCAL_FACTOR_MAX_ROWS
        rows, columns = matrix.getSize()
        if rows != columns or rows > row_cap or matrix.getComm().getSize() != 1:
            raise ValueError('BOTTOM_SCALE_LIMIT: MPI1 and <=8192 total rows required' if physical_p2_pilot
                else 'development p1 factor requires MPI1 and <=4096 total rows')
        if matrix.getType() != 'seqaij':
            raise ValueError('p1 storage budget requires an actual SeqAIJ matrix')
        info = matrix.getInfo()
        indptr, indices, values = matrix.getValuesCSR()
        payload = int(indptr.nbytes + indices.nbytes + values.nbytes)
        used, allocated = info.get('nz_used'), info.get('nz_allocated')
        if (used is None or allocated is None or not np.isfinite([used, allocated]).all()
                or used != int(used) or allocated != int(allocated)
                or used != len(values) or len(indices) != len(values)
                or allocated < used or len(indptr) != rows + 1):
            raise RuntimeError('actual SeqAIJ allocated/used NNZ is unavailable or inconsistent')
        storage = int((rows + 1) * indptr.dtype.itemsize
                      + allocated * (indices.dtype.itemsize + values.dtype.itemsize))
        allocator = float(info.get('memory', float('nan')))
        allocator_bytes = int(allocator) if np.isfinite(allocator) and allocator > 0 else None
        # Policy reserve, NOT a proven bound on unobservable PETSc/allocator objects.
        # Cover a second allocated CSR-sized buffer plus 16 MiB of object overhead.
        # The independent parent RSS gate remains authoritative for actual memory.
        if int(extra_local_bytes) < 0:
            raise ValueError("negative extra local storage budget")
        reserve = storage + 16 * 1024**2 + int(extra_local_bytes)
        matrix_budget = max(storage, allocator_bytes or 0) + reserve
        if physical_p2_pilot:
            # MUMPS COO conversion (two indices + scalar), plus bounded solve/refinement vectors.
            conversion = int(allocated * (2 * indices.dtype.itemsize + values.dtype.itemsize))
            workspace = int(16 * rows * values.dtype.itemsize)
            matrix_budget += conversion + workspace
            self.audit.update(physical_p2_pilot=True, row_cap=row_cap,
                conversion_reserve_bytes=conversion, solve_workspace_reserve_bytes=workspace,
                bottom_budget_bytes=LOCAL_FACTOR_MAX_BYTES, classification='derived_policy_budget_not_RSS')
            if matrix_budget > LOCAL_FACTOR_MAX_BYTES:
                raise RuntimeError('p2 matrix/conversion/workspace exceeds 512MiB before symbolic')
        self.audit.update(extra_local_bytes=int(extra_local_bytes), rows=int(rows), nnz=int(used), allocated_nnz=int(allocated),
                          scalar_dtype=str(values.dtype), index_dtype=str(indices.dtype),
                          row_pointer_dtype=str(indptr.dtype), matrix_csr_payload_bytes=payload,
                          matrix_allocated_csr_storage_bytes=storage,
                          matrix_petsc_allocator_bytes=allocator_bytes,
                          matrix_allocator_readable=allocator_bytes is not None,
                          matrix_unobservable_overhead_reserve_bytes=reserve,
                          matrix_storage_budget_bytes=matrix_budget,
                          matrix_storage_budget_classification='derived_policy_budget',
                          unobservable_components=['PETSc auxiliary objects', 'allocator overhead/fragmentation'],
                          reserve_is_proven_allocator_upper_bound=False,
                          mumps_memory_unit_bytes=1_000_000,
                          mumps_memory_rounding_padding_bytes=1_000_000,
                          memory_documentation='https://mumps-solver.org/doc/userguide_5.9.1.pdf#page=112')
        try:
            start = time.perf_counter()
            emit('p1_symbolic_started', {'label': label, **self.audit})
            self.factor = _MumpsFactor(matrix)
            self.factor.symbolic(matrix)
            raw = self.factor.info(extra_indices=(21, 22, 29))
            estimated = self._mb_upper(raw, '17')
            memory = resource_sample()
            predicted = matrix_budget + estimated
            self.audit.update(symbolic_raw=raw, symbolic_seconds=time.perf_counter()-start,
                              factor_estimated_padded_bytes=estimated,
                              derived_matrix_plus_estimated_factor_budget_bytes=predicted,
                              symbolic_resource=memory)
            emit('p1_symbolic_complete', dict(self.audit))
            if predicted > LOCAL_FACTOR_MAX_BYTES:
                raise RuntimeError(f'{label}: symbolic matrix+factor exceeds 512MiB')
            if memory['rss_bytes'] + estimated >= memory['launch_cap_bytes']:
                raise RuntimeError(f'{label}: symbolic prediction exceeds whole-workflow cap')
            self.factor.set_memory_limit_mb(max(1, (LOCAL_FACTOR_MAX_BYTES-matrix_budget)//1_000_000))
            start = time.perf_counter()
            self.factor.numeric(matrix)
            raw = self.factor.info(extra_indices=(21, 22, 29))
            allocated_factor = self._mb_upper(raw, '19')
            used_factor = self._mb_upper(raw, '22')
            actual = matrix_budget + max(allocated_factor, used_factor)
            self.audit.update(numeric_raw=raw, numeric_seconds=time.perf_counter()-start,
                              factor_reported_allocated_padded_bytes=allocated_factor,
                              factor_reported_used_padded_bytes=used_factor,
                              derived_matrix_plus_reported_factor_budget_bytes=actual)
            emit('p1_numeric_complete', dict(self.audit))
            if actual > LOCAL_FACTOR_MAX_BYTES:
                raise RuntimeError(f'{label}: derived matrix+reported factor budget exceeds 512MiB')
        except BaseException:
            self.destroy()
            raise

    @staticmethod
    def _mb_upper(raw: dict, key: str) -> int:
        value = raw['infog'].get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(f'MUMPS INFOG({key}) memory value is unavailable')
        return (value + 1) * 1_000_000

    def solve_lean(self, rhs: Any) -> tuple[Any, dict]:
        if self.factor is None:
            raise RuntimeError('p1 factor has been destroyed')
        started = time.perf_counter()
        solution = self.matrix.createVecRight()
        try:
            self.factor.solve_repeated(rhs, solution)
            if not np.isfinite(solution.norm()):
                raise RuntimeError('p1 solution is nonfinite')
            self.solve_count += 1
            facts = {'label': self.label, 'solve_count': self.solve_count, 'finite': True,
                     'wall_seconds_exclusive': time.perf_counter()-started}
            self.last_apply_facts = facts
            return solution, facts
        except BaseException:
            solution.destroy()
            raise

    def __call__(self, rhs: Any) -> Any:
        return self.solve_lean(rhs)[0]

    def destroy(self) -> None:
        if self.factor is not None:
            self.factor.destroy()
            self.factor = None
