"""Explicitly bounded development p1 factors with symbolic-before-numeric gates."""

from __future__ import annotations

from collections.abc import Callable
import math
import time
from typing import Any

import numpy as np

from .fullspace_physical_intermediate import LOCAL_FACTOR_MAX_BYTES, LOCAL_FACTOR_MAX_ROWS
from .fullspace_v17_p3_oracle import _MumpsFactor


LEGACY_LOCAL_MUMPS_MEMORY_POLICY = "LEGACY_LOCAL_MUMPS_MEMORY_POLICY"
SYMBOLIC_SIZED_LOCAL_MUMPS_V11 = "SYMBOLIC_SIZED_LOCAL_MUMPS_V11"
MUMPS_DECIMAL_MB = 1_000_000
MUMPS_V11_MIN_BYTES = 32 * 1024**2
MUMPS_V11_MARGIN_BYTES = 8 * 1024**2


def symbolic_sized_local_mumps_request(
    raw: dict[str, Any], *, mpi_size: int = 1,
) -> dict[str, int | str]:
    """Convert the reviewed MPI1 symbolic fields into one ICNTL(23) request.

    MUMPS reports these memory fields in decimal megabytes.  The extra one-MB
    rounding is deliberately retained from the existing bounded-factor audit;
    the request itself is then rounded up once more to a decimal megabyte.
    """

    if int(mpi_size) != 1:
        raise ValueError("SYMBOLIC_SIZED_LOCAL_MUMPS_V11 requires MPI1 INFOG semantics")
    infog = raw.get("infog")
    if not isinstance(infog, dict):
        raise RuntimeError("MEMORY_POLICY_UNSUPPORTED: MUMPS INFOG is unavailable")
    values: dict[str, int] = {}
    for key in ("16", "17"):
        value = infog.get(key)
        if type(value) is not int or value < 0:
            raise RuntimeError(
                f"MEMORY_POLICY_UNSUPPORTED: INFOG({key}) is not a non-negative integer"
            )
        values[key] = int(value)
    if values["16"] != values["17"]:
        raise RuntimeError(
            "MEMORY_POLICY_UNSUPPORTED: MPI1 INFOG(16) and INFOG(17) disagree"
        )
    estimate_bytes = MUMPS_DECIMAL_MB * (1 + max(values.values()))
    minimum_request = max(
        MUMPS_V11_MIN_BYTES,
        2 * estimate_bytes + MUMPS_V11_MARGIN_BYTES,
    )
    request_bytes = MUMPS_DECIMAL_MB * math.ceil(minimum_request / MUMPS_DECIMAL_MB)
    return {
        "policy": SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        "mpi_size": 1,
        "infog16_mb": values["16"],
        "infog17_mb": values["17"],
        "estimate_bytes": estimate_bytes,
        "minimum_request_bytes": minimum_request,
        "request_bytes": int(request_bytes),
        "request_mb": int(request_bytes // MUMPS_DECIMAL_MB),
        "unit_bytes": MUMPS_DECIMAL_MB,
        "rounding": "decimal_MB_ceiling",
    }


class BoundedP1Factor:
    """Borrow one p1 matrix, own one MUMPS factor, expose the existing solve_lean API.

    MUMPS INFOG17/19/22 are respectively estimated, allocated and used internal
    memory sums in decimal MB (MUMPS user guide). Values are rounded, so budgets
    use the next MB as an upper bound. Matrix CSR payload is reported separately
    from PETSc's allocator report and from the whole-job process-tree RSS.
    """

    def __init__(self, matrix: Any, *, label: str, resource_sample: Callable[[], dict],
                 marker: Callable[[str, dict], None], physical_p2_pilot: bool = False,
                 extra_local_bytes: int = 0, pre_numeric_gate: Callable[[dict], None] | None = None,
                 memory_policy: str = LEGACY_LOCAL_MUMPS_MEMORY_POLICY) -> None:
        self.matrix, self.label = matrix, label
        self.marker = marker
        self.pre_numeric_gate = pre_numeric_gate
        if memory_policy not in (
            LEGACY_LOCAL_MUMPS_MEMORY_POLICY,
            SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
        ):
            raise ValueError(f"unknown bounded MUMPS memory policy: {memory_policy}")
        self.memory_policy = memory_policy
        self.factor = None
        self.solve_count = 0
        self.last_apply_facts: dict = {}
        self.audit: dict = {
            'label': label,
            'bounded_development_coarse_factor': True,
            'memory_policy': memory_policy,
        }
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
            raw = self.factor.info(
                extra_indices=(21, 22, 29),
                include_local=memory_policy == SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
            )
            if memory_policy == SYMBOLIC_SIZED_LOCAL_MUMPS_V11:
                symbolic_request = symbolic_sized_local_mumps_request(
                    raw, mpi_size=matrix.getComm().getSize()
                )
                estimated = int(symbolic_request["estimate_bytes"])
                requested = int(symbolic_request["request_bytes"])
            else:
                symbolic_request = None
                estimated = self._mb_upper(raw, '17')
                requested = estimated
            memory = resource_sample()
            estimated_predicted = matrix_budget + estimated
            requested_predicted = matrix_budget + requested
            self.audit.update(symbolic_raw=raw, symbolic_seconds=time.perf_counter()-start,
                              factor_estimated_padded_bytes=estimated,
                              derived_matrix_plus_estimated_factor_budget_bytes=estimated_predicted,
                              symbolic_resource=memory)
            if symbolic_request is not None:
                self.audit.update(
                    symbolic_sized_request=symbolic_request,
                    factor_requested_padded_bytes=requested,
                    derived_matrix_plus_requested_factor_budget_bytes=requested_predicted,
                    numeric_requested_bytes=requested,
                )
            emit('p1_symbolic_complete', dict(self.audit))
            if requested_predicted > LOCAL_FACTOR_MAX_BYTES:
                raise RuntimeError(
                    f'{label}: symbolic matrix+requested factor exceeds 512MiB'
                    if symbolic_request is not None
                    else f'{label}: symbolic matrix+factor exceeds 512MiB'
                )
            if memory['rss_bytes'] + requested >= memory['launch_cap_bytes']:
                raise RuntimeError(f'{label}: symbolic prediction exceeds whole-workflow cap')
            if self.pre_numeric_gate is not None:
                self.pre_numeric_gate(dict(self.audit))
            if symbolic_request is not None:
                # ICNTL(23) is the requested per-instance decimal-MB package;
                # it is never inferred from the remaining 512 MiB budget.
                request_mb = int(symbolic_request["request_mb"])
                try:
                    self.factor.set_memory_limit_mb(request_mb)
                    readback = self.factor.get_icntl(23)
                except BaseException as exc:
                    raise RuntimeError(
                        f"MEMORY_POLICY_UNSUPPORTED: ICNTL(23) set/readback failed: {exc}"
                    ) from exc
                if readback != request_mb:
                    raise RuntimeError(
                        f"MEMORY_POLICY_UNSUPPORTED: ICNTL(23) readback {readback} != {request_mb}"
                    )
                compaction = self.factor.try_get_icntl(49)
                if compaction["supported"]:
                    try:
                        self.factor.set_icntl(49, 1)
                        after = self.factor.get_icntl(49)
                    except BaseException as exc:
                        compaction.update(
                            status="COMPACTION_UNSUPPORTED",
                            set_error=f"{type(exc).__name__}: {exc}",
                        )
                    else:
                        compaction.update(
                            status="COMPACTION_REQUESTED" if after == 1 else "COMPACTION_NOT_CONFIRMED",
                            value_after=after,
                        )
                else:
                    compaction["status"] = "COMPACTION_UNSUPPORTED"
                self.audit.update(
                    icntl23_requested_mb=request_mb,
                    icntl23_readback_mb=readback,
                    icntl49=compaction,
                )
                emit('p1_memory_controls_set', dict(self.audit))
            else:
                self.factor.set_memory_limit_mb(
                    max(1, (LOCAL_FACTOR_MAX_BYTES-matrix_budget)//1_000_000)
                )
            start = time.perf_counter()
            emit('p1_numeric_started', dict(self.audit))
            try:
                self.factor.numeric(matrix)
            except BaseException as exc:
                failure_raw = None
                failure_raw_error = None
                try:
                    failure_raw = self.factor.info(
                        extra_indices=(21, 22, 29),
                        include_local=memory_policy == SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
                    )
                except BaseException as info_exc:
                    failure_raw_error = f"{type(info_exc).__name__}: {info_exc}"
                failure_codes = {}
                if isinstance(failure_raw, dict):
                    infog = failure_raw.get("infog")
                    info = failure_raw.get("info")
                    if isinstance(infog, dict):
                        for index in (1, 2, 9, 19):
                            if str(index) in infog:
                                failure_codes[f"INFOG({index})"] = infog[str(index)]
                    if isinstance(info, dict) and "2" in info:
                        failure_codes["INFO(2)"] = info["2"]
                numeric_error_codes = {
                    key: value for key, value in failure_codes.items()
                    if key in ("INFO(1)", "INFOG(1)")
                }
                self.audit.update(
                    numeric_seconds=time.perf_counter()-start,
                    numeric_exception_type=type(exc).__name__,
                    numeric_exception=str(exc),
                    numeric_failure_raw=failure_raw,
                    numeric_failure_raw_error=failure_raw_error,
                    numeric_failure_codes=failure_codes,
                    numeric_failure_error_codes=numeric_error_codes,
                    numeric_failure_classification=(
                        "LOCAL_WORKSPACE_LIMIT"
                        if any(value in (-9, -19) for value in numeric_error_codes.values())
                        else "NUMERIC_FAILED"
                    ),
                )
                emit('p1_numeric_failed', dict(self.audit))
                raise
            raw = self.factor.info(
                extra_indices=(21, 22, 29),
                include_local=memory_policy == SYMBOLIC_SIZED_LOCAL_MUMPS_V11,
            )
            allocated_factor = self._mb_upper(raw, '19')
            used_factor = self._mb_upper(raw, '22')
            actual = matrix_budget + max(allocated_factor, used_factor)
            self.audit.update(numeric_raw=raw, numeric_seconds=time.perf_counter()-start,
                              factor_reported_allocated_padded_bytes=allocated_factor,
                              factor_reported_used_padded_bytes=used_factor,
                              derived_matrix_plus_reported_factor_budget_bytes=actual)
            if symbolic_request is not None:
                info = raw.get("info")
                infog = raw.get("infog")
                info1 = info.get("1") if isinstance(info, dict) else None
                infog1 = infog.get("1") if isinstance(infog, dict) else None
                warning_facts = {
                    "info1": info1,
                    "infog1": infog1,
                    "info_warning": isinstance(info1, int) and info1 > 0,
                    "infog_warning": isinstance(infog1, int) and infog1 > 0,
                    "compaction_warning": any(
                        isinstance(value, int) and value > 0 and value & 4
                        for value in (info1, infog1)
                    ),
                    "warning_encoding": "positive_INFO1_bits_and_MPI1_INFOG1_sum",
                }
                self.audit["numeric_warnings"] = warning_facts
                if warning_facts["compaction_warning"]:
                    self.audit["icntl49"]["status"] = "COMPACTION_WARNING"
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
