"""Owner-local positive fixed-LOR service on an active condensed trace."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import cho_factor, cho_solve

from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
)
from .hcurl_fixed_lor_cell_bridge import FixedP6LORCellBridge

__all__ = ("FixedP6LORTraceService", "build_fixed_lor_trace_service")
_TOL, _MAX_ROWS, _TINY = 1.0e-10, 432, 1.0e-30


@dataclass
class _Cell:
    factor_key: tuple[str, str]
    positions: np.ndarray
    weights: np.ndarray | None = None


@dataclass
class _Factor:
    chol: np.ndarray
    lower: bool
    rows: int
    solve_relative: float
    hermitian: float


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), _TINY))


def _positive_pair(value: Any, name: str) -> tuple[float, float]:
    values = np.asarray(value, dtype=np.float64).reshape(-1)
    invalid = (
        values.size != 2
        or not np.all(np.isfinite(values))
        or values[0] <= 0.0
        or abs(values[1]) > 1.0e-12 * max(1.0, values[0])
    )
    if invalid:
        raise ValueError(f"{name} must be strictly positive real")
    return float(values[0]), float(values[1])


def _array_fingerprint(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.complex128)
    digest = hashlib.sha256(str(array.shape).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def _factor_key(
    class_key: tuple[Any, ...],
    bridge: FixedP6LORCellBridge,
    expansion: np.ndarray,
) -> tuple[str, str]:
    cell = bridge.audit["cell"]
    identity = repr(
        (
            class_key,
            cell.get("widths"),
            cell.get("cell_info"),
            cell.get("curl_coefficient"),
            cell.get("mass_coefficient"),
        )
    )
    return repr(identity), _array_fingerprint(expansion)


def _scatter_values(scatter, source, target, addv, mode) -> None:
    scatter.scatter(source, target, addv=addv, mode=mode)


def _make_factor(block: np.ndarray) -> _Factor:
    if block.shape[0] > _MAX_ROWS or not np.all(np.isfinite(block)):
        raise ValueError("active local factor is invalid or exceeds row limit")
    hermitian = np.linalg.norm(block - block.conj().T) / max(
        np.linalg.norm(block), _TINY
    )
    if not np.isfinite(hermitian) or hermitian > _TOL:
        raise RuntimeError("active local factor is not Hermitian")
    chol, lower = cho_factor(block, lower=True, check_finite=True)
    probe = np.ones(block.shape[0], dtype=np.complex128)
    solve_relative = _relative(
        block @ cho_solve((chol, lower), probe, check_finite=True), probe
    )
    if not np.isfinite(solve_relative) or solve_relative > _TOL:
        raise RuntimeError("active local Cholesky solve is not qualified")
    return _Factor(
        chol=chol,
        lower=bool(lower),
        rows=int(block.shape[0]),
        solve_relative=solve_relative,
        hermitian=hermitian,
    )


class FixedP6LORTraceService:
    """Owner-local P+ solves for constrained p6/LOR trace cells."""

    def __init__(
        self,
        *,
        cells: tuple[_Cell, ...],
        factors: dict[tuple[str, str], _Factor],
        scatter: PETSc.Scatter,
        local_source: PETSc.Vec,
        local_target: PETSc.Vec,
        global_rows: int,
        ownership: tuple[int, int],
        audit: dict[str, Any],
    ) -> None:
        self._cells, self._factors = cells, factors
        self._scatter: PETSc.Scatter | None = scatter
        self._local_source: PETSc.Vec | None = local_source
        self._local_target: PETSc.Vec | None = local_target
        self._global_rows, self._ownership = int(global_rows), ownership
        self._destroyed = False
        self.audit = audit

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def _require_alive(self) -> None:
        if self._destroyed:
            raise RuntimeError("fixed LOR trace service is destroyed")

    def _check_vector(self, vector: PETSc.Vec, name: str) -> None:
        if int(vector.getSize()) != self._global_rows:
            raise ValueError(f"{name} has the wrong global active-trace size")
        if tuple(map(int, vector.getOwnershipRange())) != self._ownership:
            raise ValueError(f"{name} has the wrong PETSc ownership range")

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._apply(source, target)
        self.audit["solve_count"] += 1

    def apply(
        self,
        _pc: PETSc.PC | None,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self._apply(source, target)

    def _apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._require_alive()
        self._check_vector(source, "source")
        self._check_vector(target, "target")
        scatter, local_source = self._scatter, self._local_source
        local_target = self._local_target
        assert scatter is not None and local_source is not None
        assert local_target is not None
        _scatter_values(
            scatter,
            source,
            local_source,
            PETSc.InsertMode.INSERT_VALUES,
            PETSc.ScatterMode.FORWARD,
        )
        target.set(0.0)
        source_values = local_source.getArray(readonly=True)
        local_target.set(0.0)
        target_values = local_target.getArray()
        for cell in self._cells:
            factor = self._factors[cell.factor_key]
            solution = cho_solve(
                (factor.chol, factor.lower),
                source_values[cell.positions],
                check_finite=True,
            )
            np.add.at(target_values, cell.positions, solution * cell.weights)
        _scatter_values(
            scatter,
            local_target,
            target,
            PETSc.InsertMode.ADD_VALUES,
            PETSc.ScatterMode.REVERSE,
        )
        self.audit["apply_count"] += 1

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._scatter.destroy()
        self._local_target.destroy()
        self._local_source.destroy()
        self._factors.clear()
        self._cells = ()
        self._scatter = self._local_source = self._local_target = None
        self._destroyed = True
        self.audit["destroyed"] = True


def build_fixed_lor_trace_service(
    condensed: AssemblyTimeCondensedSystem,
    bridge_by_class: Mapping[tuple[Any, ...], FixedP6LORCellBridge],
) -> FixedP6LORTraceService:
    """Build an active-trace P+ service without a global fine matrix."""

    started = perf_counter()
    build_audit = condensed.build_audit
    if int(condensed.appended_rows) != 0:
        raise ValueError("the trace service requires appended_rows=0")
    retained = condensed.retained_local_schur_by_class
    if retained is None or not build_audit["retained_local_schur_enabled"]:
        raise ValueError("retained local Schur classes are required")
    if (
        condensed.matrix is not None
        or build_audit["matrix_materialized"] is not False
        or build_audit["global_active_F_allocated"] is not False
    ):
        raise ValueError("the trace service requires an action-only condensed system")

    comm = condensed.comm
    template = condensed.create_active_vector()
    global_rows, ownership = int(template.getSize()), tuple(
        map(int, template.getOwnershipRange())
    )
    local_union: set[int] = set()
    pending: list[tuple[np.ndarray, tuple[str, str]]] = []
    factors: dict[tuple[str, str], _Factor] = {}
    checked_classes: set[tuple[Any, ...]] = set()
    prod_bridge_max = hermitian_max = factor_solve_max = 0.0
    local_cells = condensed.cell_recovery_maps
    for cell in local_cells:
        class_key = cell.class_key
        bridge = bridge_by_class.get(class_key)
        if bridge is None:
            raise KeyError(f"missing bridge for class {class_key!r}")
        if bridge.destroyed or not bridge.audit.get("pass", False):
            raise RuntimeError("every bridge must be alive and audited")
        coefficients = bridge.audit["cell"]
        _positive_pair(coefficients["curl_coefficient"], "curl_coefficient")
        _positive_pair(coefficients["mass_coefficient"], "mass_coefficient")
        if not (
            coefficients.get("ordinary_defaults_unchanged", False)
            and coefficients.get("physics_unchanged", False)
        ):
            raise RuntimeError("bridge ordinary/physics identity is not qualified")
        production = np.asarray(retained[class_key], dtype=np.complex128)
        fine, mapped_lor, trace_transfer = (
            bridge.fine_trace_operator,
            bridge.lor_trace_operator,
            bridge.trace_transfer,
        )
        if fine is None or mapped_lor is None or trace_transfer is None:
            raise RuntimeError("bridge arrays are unavailable")
        fine = np.asarray(fine, dtype=np.complex128)
        if class_key not in checked_classes:
            if production.shape != fine.shape:
                raise RuntimeError("production and bridge trace shapes differ")
            prod_bridge_max = max(prod_bridge_max, _relative(fine, production))
            if prod_bridge_max > _TOL:
                raise RuntimeError("production retained Schur is not bridge-bound")
            checked_classes.add(class_key)
        active_ids, sparse_expansion, _ = _cell_trace_expansion(
            cell.trace_original_dofs, condensed.trace_constraints
        )
        active_ids = np.asarray(active_ids, dtype=PETSc.IntType)
        if len(np.unique(active_ids)) != len(active_ids):
            raise RuntimeError("a cell active expansion contains duplicate rows")
        expansion = np.asarray(sparse_expansion.toarray(), dtype=np.complex128)
        if expansion.shape[1] > _MAX_ROWS:
            raise ValueError("active local expansion exceeds the bounded row limit")
        local_union.update(map(int, active_ids))
        factor_key = _factor_key(class_key, bridge, expansion)
        if factor_key not in factors:
            mapped = np.asarray(
                np.asarray(trace_transfer).conj().T
                @ (np.asarray(mapped_lor) @ np.asarray(trace_transfer)),
                dtype=np.complex128,
            )
            block = expansion.conj().T @ mapped @ expansion
            factor = _make_factor(block)
            factors[factor_key] = factor
            hermitian_max = max(hermitian_max, factor.hermitian)
            factor_solve_max = max(factor_solve_max, factor.solve_relative)
            del mapped, block
        pending.append((active_ids, factor_key))
        del expansion

    union = np.asarray(sorted(local_union), dtype=PETSc.IntType)
    cells = [
        _Cell(
            factor_key=factor_key,
            positions=np.searchsorted(union, active_ids),
        )
        for active_ids, factor_key in pending
    ]
    local_source = PETSc.Vec().createSeq(len(union), comm=PETSc.COMM_SELF)
    local_target = local_source.duplicate()
    global_is = PETSc.IS().createGeneral(union, comm=PETSc.COMM_SELF)
    local_is = PETSc.IS().createStride(
        len(union), first=0, step=1, comm=PETSc.COMM_SELF
    )
    scatter = PETSc.Scatter().create(template, global_is, local_source, local_is)
    global_is.destroy()
    local_is.destroy()
    multiplicity = template.duplicate()
    multiplicity.set(0.0)
    local_counts = local_source.getArray()
    local_counts[:] = 0.0
    for cell in cells:
        np.add.at(local_counts, cell.positions, 1.0)
    _scatter_values(
        scatter,
        local_source,
        multiplicity,
        PETSc.InsertMode.ADD_VALUES,
        PETSc.ScatterMode.REVERSE,
    )
    _scatter_values(
        scatter,
        multiplicity,
        local_source,
        PETSc.InsertMode.INSERT_VALUES,
        PETSc.ScatterMode.FORWARD,
    )
    union_counts = np.array(local_source.getArray(readonly=True), copy=True)
    if union_counts.size and (
        not np.all(np.isfinite(union_counts)) or np.any(union_counts <= 0.0)
    ):
        raise RuntimeError("active cell coverage is incomplete")
    local_source.set(0.0)
    local_weights = local_source.getArray()
    for cell in cells:
        cell.weights = np.asarray(
            1.0 / union_counts[cell.positions], dtype=PETSc.ScalarType
        )
        np.add.at(local_weights, cell.positions, cell.weights)
    weight_sum = template.duplicate()
    weight_sum.set(0.0)
    _scatter_values(
        scatter,
        local_source,
        weight_sum,
        PETSc.InsertMode.ADD_VALUES,
        PETSc.ScatterMode.REVERSE,
    )
    owned_weights = np.asarray(weight_sum.getArray(readonly=True))
    coverage = np.asarray(multiplicity.getArray(readonly=True))
    coverage_real = coverage.real
    coverage_imag_max = (
        float(np.max(np.abs(coverage.imag))) if coverage.size else 0.0
    )
    if coverage.size and (
        not np.all(np.isfinite(coverage_real))
        or np.any(coverage_real <= 0.0)
        or not np.isfinite(coverage_imag_max)
        or coverage_imag_max > 1.0e-14
    ):
        raise RuntimeError("owned active-row coverage is incomplete")
    local_pou_error = (
        float(np.max(np.abs(owned_weights - 1.0))) if owned_weights.size else 0.0
    )
    pou_error = float(comm.allreduce(local_pou_error, op=MPI.MAX))
    if pou_error > _TOL:
        raise RuntimeError("active POU weights do not sum to one")
    multiplicity.destroy()
    weight_sum.destroy()
    template.destroy()

    work_payload = 2 * len(union) * np.dtype(PETSc.ScalarType).itemsize
    factor_rows = [factor.rows for factor in factors.values()]
    owned_start, owned_stop = ownership
    ghost_rows = int(np.count_nonzero((union < owned_start) | (union >= owned_stop)))
    retained_bytes = int(
        sum(factor.chol.nbytes for factor in factors.values())
        + sum(cell.positions.nbytes + cell.weights.nbytes for cell in cells)
    )
    cell_count_local = len(cells)
    class_count_local = len({cell.factor_key[0] for cell in cells})
    prod_bridge_global = float(comm.allreduce(prod_bridge_max, op=MPI.MAX))
    hermitian_global = float(comm.allreduce(hermitian_max, op=MPI.MAX))
    factor_solve_global = float(comm.allreduce(factor_solve_max, op=MPI.MAX))
    local_coverage_min = (
        float(np.min(coverage.real)) if coverage.size else np.inf
    )
    global_coverage_min = float(comm.allreduce(local_coverage_min, op=MPI.MIN))
    audit = {
        "schema_version": "task040.fixed-lor.l2b.v1",
        "status": "fixed_p6_lor_trace_component_service_ready",
        "pass": True,
        "scope": "component_service_only_not_h10_h5_or_5nm_signal",
        "cell_count_local": cell_count_local,
        "cell_count_global": int(comm.allreduce(cell_count_local, op=MPI.SUM)),
        "class_count_local": class_count_local,
        "class_count_rank_sum": int(comm.allreduce(class_count_local, op=MPI.SUM)),
        "factor_count_local": len(factors),
        "factor_count_rank_sum": int(comm.allreduce(len(factors), op=MPI.SUM)),
        "factor_cache_reuse_local": cell_count_local - len(factors),
        "factor_rows_local": tuple(factor_rows),
        "max_local_factor_rows": max(factor_rows, default=0),
        "prod_vs_bridge_max_relative": prod_bridge_global,
        "hermitian_max_relative": hermitian_global,
        "factor_solve_relative_max": factor_solve_global,
        "coverage_global_min": (
            None if np.isinf(global_coverage_min) else global_coverage_min
        ),
        "owned_row_range": ownership,
        "local_union_rows": len(union),
        "local_ghost_rows": ghost_rows,
        "global_active_rows": global_rows,
        "pou_weight_sum_max_error": pou_error,
        "retained_numpy_factor_map_bytes_not_peak": retained_bytes,
        "retained_work_vector_payload_bytes_not_peak": work_payload,
        "global_F": False,
        "global_AIJ": False,
        "global_factor": False,
        "numeric_allgather": False,
        "full_basis_replication": False,
        "bridge_retained": False,
        "mapped_dense_retained": False,
        "destroy_supported": True,
        "destroyed": False,
        "apply_count": 0,
        "solve_count": 0,
        "build_wall_seconds": float(perf_counter() - started),
    }
    return FixedP6LORTraceService(
        cells=tuple(cells),
        factors=factors,
        scatter=scatter,
        local_source=local_source,
        local_target=local_target,
        global_rows=global_rows,
        ownership=ownership,
        audit=audit,
    )
