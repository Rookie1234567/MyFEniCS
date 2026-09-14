"""Action-only p6 trace/port condensation.

This module is the small numerical core for the V19 p6 path.  The volume
operator is supplied by :mod:`hcurl_assembly_time_condensation`, which keeps
one local ``S_V`` and one local LU per oriented cell class.  The code here
adds the carrier blocks without allocating a global p6 matrix:

``[S_V, Bhat; -Dhat, Hhat]`` is evaluated by cell gather/multiply/scatter,
while ``Hhat`` is the only dense object and is only ``nport`` by ``nport``.

The original carrier block ``H_p`` is retained separately.  In particular,
the BAL_H bridge below deliberately solves with ``H_p`` and never substitutes
``Hhat``.  All arrays use the native non-Hermitian signs from
``[[V, B], [-D, H_p]]``; no conjugate transpose is inferred for ``D``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from petsc4py import PETSc
from scipy import sparse
from scipy.linalg import lu_factor, lu_solve

from .hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    _cell_trace_expansion,
    _strict_local_lu,
)


def _complex_matrix(value: Any, name: str, *, shape: tuple[int, int] | None = None) -> np.ndarray:
    """Copy and validate one finite complex128 matrix."""

    result = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    if result.ndim != 2:
        raise ValueError(f"{name} must be two-dimensional")
    if shape is not None and result.shape != shape:
        raise ValueError(f"{name} has shape {result.shape}, expected {shape}")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def _complex_vector(value: Any, name: str, *, size: int | None = None) -> np.ndarray:
    """Copy and validate one finite complex128 vector."""

    result = np.ascontiguousarray(np.asarray(value, dtype=np.complex128)).reshape(-1)
    if size is not None and result.shape != (size,):
        raise ValueError(f"{name} has shape {result.shape}, expected {(size,)}")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def _readonly(value: np.ndarray) -> np.ndarray:
    """Return a contiguous readonly array owned by the caller."""

    result = np.ascontiguousarray(value, dtype=np.complex128)
    result.setflags(write=False)
    return result


def _borrow_matrix(value: Any, name: str, *, shape: tuple[int, int] | None = None) -> np.ndarray:
    """Validate a retained class array without making a per-cell copy."""

    result = np.asarray(value, dtype=np.complex128)
    if result.ndim != 2:
        raise ValueError(f"{name} must be two-dimensional")
    if shape is not None and result.shape != shape:
        raise ValueError(f"{name} has shape {result.shape}, expected {shape}")
    if not np.isfinite(result).all():
        raise ValueError(f"{name} contains non-finite values")
    return result


def _factored_matrix_action(
    factor: tuple[np.ndarray, np.ndarray],
    values: np.ndarray,
) -> np.ndarray:
    """Apply the original matrix represented by one SciPy LU factor."""

    rhs = np.asarray(values, dtype=np.complex128)
    one_column = rhs.ndim == 1
    if one_column:
        rhs = rhs[:, None]
    lu, pivots = factor
    dimension = int(lu.shape[0])
    lower = np.tril(lu, k=-1) + np.eye(dimension, dtype=np.complex128)
    upper = np.triu(lu)
    permuted = lower @ (upper @ rhs)
    permutation = np.arange(dimension)
    for row, pivot in enumerate(pivots):
        permutation[[row, int(pivot)]] = permutation[[int(pivot), row]]
    result = np.ascontiguousarray(permuted[np.argsort(permutation)])
    return result[:, 0] if one_column else result


def _operation_relative(norm: float, scale: float, *, absolute_tolerance: float = 1.0e-12) -> float:
    """Use an explicit absolute rule when an operation has zero scale."""

    norm = float(norm)
    scale = float(scale)
    if scale > np.finfo(float).tiny:
        return norm / scale
    return 0.0 if norm <= float(absolute_tolerance) else float("inf")


def _array_sha256(value: np.ndarray) -> str:
    """Hash one native little-endian array without gathering any matrix."""

    array = np.ascontiguousarray(value, dtype=np.complex128)
    return hashlib.sha256(
        repr((array.shape, str(array.dtype))).encode()
        + array.tobytes(order="C")
    ).hexdigest()


@dataclass(frozen=True)
class P6CellPortTerms:
    """Port couplings belonging to one owned cell.

    ``Bi``/``Di`` are the local internal couplings.  Optional ``Bt``/``Dt``
    are local trace couplings in the cell's original trace ordering.  ``H``
    is an optional direct local contribution to the original port block; it
    is merged into ``H_p`` at ``port_indices`` before ``Hhat`` is formed.
    """

    Bi: np.ndarray
    Di: np.ndarray
    port_indices: np.ndarray
    Bt: np.ndarray | None = None
    Dt: np.ndarray | None = None
    H: np.ndarray | None = None


@dataclass(frozen=True)
class P6DirectTracePortTerms:
    """Carrier entries whose volume rows are trace rows, before MPC reduction."""

    port_index: int
    B_original_rows: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=PETSc.IntType))
    B_values: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.complex128))
    D_original_rows: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=PETSc.IntType))
    D_values: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.complex128))


@dataclass(frozen=True)
class CondensedPhysicalCell:
    """Dense local result of eliminating one internal block.

    This is intentionally small and is also useful as the reference-free
    algebra oracle in tests.  ``Xit`` and ``XiB`` are ``V_ii^{-1}V_it`` and
    ``V_ii^{-1}B_i`` respectively.
    """

    S_V: np.ndarray
    Bhat: np.ndarray
    Dhat: np.ndarray
    Hhat: np.ndarray
    Xit: np.ndarray
    XiB: np.ndarray
    trace_from_interior: np.ndarray
    interior_lu: tuple[np.ndarray, np.ndarray]

    def solve_interior(self, rhs: Any) -> np.ndarray:
        """Apply the cached local LU to one or more internal RHS columns."""

        return np.ascontiguousarray(
            lu_solve(self.interior_lu, _complex_vector(rhs, "interior RHS")
                     if np.asarray(rhs).ndim == 1
                     else _complex_matrix(rhs, "interior RHS"))
        )

    def recover(self, trace: Any, alpha: Any, rhs_i: Any | None = None) -> np.ndarray:
        """Recover internal coefficients for a retained ``(trace, alpha)``."""

        trace_values = _complex_vector(trace, "local trace", size=self.S_V.shape[0])
        alpha_values = _complex_vector(alpha, "local port values", size=self.Bhat.shape[1])
        rhs_values = (
            np.zeros(self.Xit.shape[0], dtype=np.complex128)
            if rhs_i is None
            else _complex_vector(rhs_i, "internal RHS", size=self.Xit.shape[0])
        )
        return np.ascontiguousarray(
            lu_solve(self.interior_lu, rhs_values)
            - self.Xit @ trace_values
            - self.XiB @ alpha_values
        )


def condense_physical_cell_blocks(
    Vii: Any,
    Vit: Any,
    Vti: Any,
    Vtt: Any,
    Bi: Any,
    Bt: Any,
    Di: Any,
    Dt: Any,
    H: Any,
    *,
    strict_local_checks: bool = True,
) -> CondensedPhysicalCell:
    """Eliminate ``V_ii`` from a complete non-Hermitian local tensor.

    The caller must provide the already-summed physical ``V`` blocks.  This
    order matters: ``Schur(curl+mass)`` is not generally the sum of two
    separate Schur complements.  The returned formulas are

    ``S_V=Vtt-Vti Vii^-1 Vit``;
    ``Bhat=Bt-Vti Vii^-1 Bi``;
    ``Dhat=Dt-Di Vii^-1 Vit``;
    ``Hhat=H+Di Vii^-1 Bi``.
    """

    vii = _complex_matrix(Vii, "Vii")
    if vii.shape[0] != vii.shape[1] or vii.shape[0] == 0:
        raise ValueError("Vii must be a non-empty square matrix")
    ni = vii.shape[0]
    vit = _complex_matrix(Vit, "Vit")
    vti = _complex_matrix(Vti, "Vti")
    vtt = _complex_matrix(Vtt, "Vtt")
    bi = _complex_matrix(Bi, "Bi")
    bt = _complex_matrix(Bt, "Bt")
    di = _complex_matrix(Di, "Di")
    dt = _complex_matrix(Dt, "Dt")
    h = _complex_matrix(H, "H")
    nt = vit.shape[1]
    np_ = bi.shape[1]
    expected = {
        "Vti": (nt, ni),
        "Vtt": (nt, nt),
        "Bi": (ni, np_),
        "Bt": (nt, np_),
        "Di": (np_, ni),
        "Dt": (np_, nt),
        "H": (np_, np_),
    }
    for name, shape in expected.items():
        value = {"Vti": vti, "Vtt": vtt, "Bi": bi, "Bt": bt,
                 "Di": di, "Dt": dt, "H": h}[name]
        if value.shape != shape:
            raise ValueError(f"{name} has shape {value.shape}, expected {shape}")
    if strict_local_checks:
        factor, _residual = _strict_local_lu(vii)
    else:
        factor = lu_factor(vii, check_finite=True)
    xit = np.ascontiguousarray(lu_solve(factor, vit, check_finite=True))
    xib = np.ascontiguousarray(lu_solve(factor, bi, check_finite=True))
    trace_from_interior = np.ascontiguousarray(-vti @ lu_solve(factor, np.eye(ni, dtype=np.complex128)))
    return CondensedPhysicalCell(
        S_V=_readonly(vtt - vti @ xit),
        Bhat=_readonly(bt - vti @ xib),
        Dhat=_readonly(dt - di @ xit),
        Hhat=_readonly(h + di @ xib),
        Xit=_readonly(xit),
        XiB=_readonly(xib),
        trace_from_interior=_readonly(trace_from_interior),
        interior_lu=factor,
    )


@dataclass(frozen=True)
class _CellActionData:
    original_interiors: np.ndarray
    original_trace: np.ndarray
    active_ids: np.ndarray
    expansion: sparse.csr_matrix
    class_key: tuple[Any, ...]
    S_V: np.ndarray
    recovery: np.ndarray
    trace_from_interior: np.ndarray
    interior_lu: tuple[np.ndarray, np.ndarray]
    Bi: np.ndarray
    Bt: np.ndarray
    Di: np.ndarray
    Dt: np.ndarray
    ports: np.ndarray
    Bhat: np.ndarray
    Dhat: np.ndarray
    XiB: np.ndarray
    Hlocal: np.ndarray


def _normalise_port_terms(
    term: P6CellPortTerms | None,
    *,
    ni: int,
    nt: int,
    appended_rows: int,
    name: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate one cell's optional carrier block and fill omitted blocks."""

    if term is None:
        ports = np.empty(0, dtype=PETSc.IntType)
        return (
            np.zeros((ni, 0), dtype=np.complex128),
            np.zeros((nt, 0), dtype=np.complex128),
            np.zeros((0, ni), dtype=np.complex128),
            np.zeros((0, nt), dtype=np.complex128),
            ports,
            np.zeros((0, 0), dtype=np.complex128),
        )
    ports = np.ascontiguousarray(np.asarray(term.port_indices, dtype=PETSc.IntType)).reshape(-1)
    if len(np.unique(ports)) != len(ports) or np.any(ports < 0) or np.any(ports >= appended_rows):
        raise ValueError(f"{name}.port_indices are outside the appended port block")
    np_ = len(ports)
    bi = _complex_matrix(term.Bi, f"{name}.Bi", shape=(ni, np_))
    di = _complex_matrix(term.Di, f"{name}.Di", shape=(np_, ni))
    bt = np.zeros((nt, np_), dtype=np.complex128) if term.Bt is None else _complex_matrix(term.Bt, f"{name}.Bt", shape=(nt, np_))
    dt = np.zeros((np_, nt), dtype=np.complex128) if term.Dt is None else _complex_matrix(term.Dt, f"{name}.Dt", shape=(np_, nt))
    h = np.zeros((np_, np_), dtype=np.complex128) if term.H is None else _complex_matrix(term.H, f"{name}.H", shape=(np_, np_))
    return bi, bt, di, dt, ports, h


def _as_direct_term(value: P6DirectTracePortTerms, port_count: int) -> P6DirectTracePortTerms:
    port = int(value.port_index)
    if port < 0 or port >= port_count:
        raise ValueError("direct trace port index is outside H_p")
    b_rows = np.ascontiguousarray(np.asarray(value.B_original_rows, dtype=PETSc.IntType)).reshape(-1)
    b_values = _complex_vector(value.B_values, "direct B values", size=len(b_rows))
    d_rows = np.ascontiguousarray(np.asarray(value.D_original_rows, dtype=PETSc.IntType)).reshape(-1)
    d_values = _complex_vector(value.D_values, "direct D values", size=len(d_rows))
    return P6DirectTracePortTerms(port, b_rows, b_values, d_rows, d_values)


class P6CellCondensedAction:
    """Matrix-free action on independent p6 trace plus original ports.

    ``condensed`` must come from
    ``build_unconstrained_assembly_time_condensation(...,
    materialize_global_matrix=False, retain_local_schur_for_matrix_free=True)``.
    The class borrows its local LU/recovery/trace Schur caches and owns only
    the additional carrier arrays.  It is safe to use with a PETSc Python
    matrix or directly with global NumPy vectors in MPI1 tests.
    """

    def __init__(
        self,
        condensed: AssemblyTimeCondensedSystem,
        *,
        H_p: Any,
        port_terms: Mapping[int, P6CellPortTerms] | None = None,
        direct_trace_terms: Sequence[P6DirectTracePortTerms] = (),
        owns_condensed: bool = False,
    ) -> None:
        if condensed.matrix is not None:
            raise ValueError("p6 action-only condensation cannot borrow a materialized matrix")
        retained = condensed.retained_local_schur_by_class
        if retained is None:
            raise ValueError("p6 action-only condensation requires retained local Schur classes")
        self.condensed = condensed
        self.owns_condensed = bool(owns_condensed)
        # Hlocal contributions are merged into this original carrier block
        # below.  Own the copy explicitly so construction never mutates the
        # caller's carrier array; the large class payloads remain borrowed.
        self._H_p = np.array(_complex_matrix(H_p, "H_p"), dtype=np.complex128, copy=True, order="C")
        if self._H_p.shape != (condensed.appended_rows, condensed.appended_rows):
            raise ValueError("H_p shape differs from the appended port block")
        self._port_terms = dict(port_terms or {})
        unknown_cells = set(self._port_terms).difference(range(len(condensed.cell_recovery_maps)))
        if unknown_cells:
            raise ValueError(f"port terms refer to unknown cells: {sorted(unknown_cells)}")
        self._cells: tuple[_CellActionData, ...] = self._build_cells(retained)
        # Optional local H blocks are direct contributions to the original
        # carrier block.  Merge them before freezing H_p so that both the
        # native A6 action and the BAL_H bridge use the same original block;
        # Hhat then receives only the internal-elimination correction.
        for cell in self._cells:
            if len(cell.ports):
                self._H_p[np.ix_(cell.ports, cell.ports)] += cell.Hlocal
        self._direct_terms = tuple(
            _as_direct_term(term, condensed.appended_rows)
            for term in direct_trace_terms
        )
        self._direct_B_original: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_D_original: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_B_active: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_D_active: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._prepare_direct_terms()
        self._direct_terms = ()
        self._Hhat = self._H_p.copy()
        for cell in self._cells:
            if len(cell.ports):
                self._Hhat[np.ix_(cell.ports, cell.ports)] += cell.Di @ cell.XiB
        self._Hhat = _readonly(self._Hhat)
        self._hp_solve_count = 0
        self._apply_count = 0
        self._destroyed = False
        self._matrix: PETSc.Mat | None = None
        self._audit = {
            "schema_version": "task039extra.v19.p6-cell-condensed-action.v1",
            "matrix_materialized": False,
            "global_s6_allocated": False,
            "global_a6_allocated": False,
            "global_dense_trace_port_block_allocated": False,
            "local_cell_count": len(self._cells),
            "local_class_count": len(retained),
            "active_trace_rows": int(condensed.active_rows),
            "appended_port_rows": int(condensed.appended_rows),
            "H_p_is_original_carrier_block": True,
            "Hhat_is_retained_small_dense_block": True,
            "shared_S_V_buffer_count": len({id(cell.S_V) for cell in self._cells}),
            "shared_recovery_buffer_count": len({id(cell.recovery) for cell in self._cells}),
            "shared_LU_factor_buffer_count": len({id(cell.interior_lu[0]) for cell in self._cells}),
            "class_cache_shared_across_cells": True,
            "direct_trace_B_entry_count": int(sum(len(rows) for rows, _values in self._direct_B_original.values())),
            "direct_trace_D_entry_count": int(sum(len(rows) for rows, _values in self._direct_D_original.values())),
            "apply_count": 0,
            "hp_solve_count": 0,
        }
        condensed.build_audit.setdefault("p6_cell_condensed_action", dict(self._audit))

    def _build_cells(self, retained: Mapping[tuple[Any, ...], np.ndarray]) -> tuple[_CellActionData, ...]:
        result: list[_CellActionData] = []
        constraints = self.condensed.trace_constraints
        for index, cell in enumerate(self.condensed.cell_recovery_maps):
            schur = _borrow_matrix(retained[cell.class_key], "retained local S_V")
            ni = len(cell.interior_original_dofs)
            nt = len(cell.trace_original_dofs)
            if schur.shape != (nt, nt):
                raise ValueError("retained local S_V shape differs from the cell trace")
            active_ids, expansion, _identity = _cell_trace_expansion(
                np.asarray(cell.trace_original_dofs, dtype=PETSc.IntType), constraints
            )
            bi, bt, di, dt, ports, h = _normalise_port_terms(
                self._port_terms.get(index),
                ni=ni,
                nt=nt,
                appended_rows=self.condensed.appended_rows,
                name=f"port_terms[{index}]",
            )
            recovery = _borrow_matrix(
                self.condensed.interior_from_trace_by_class[cell.class_key],
                "interior recovery",
                shape=(ni, nt),
            )
            trace_from_interior = _borrow_matrix(
                self.condensed.trace_from_interior_rhs_by_class[cell.class_key],
                "trace RHS projection",
                shape=(nt, ni),
            )
            factor = self.condensed.interior_lu_by_class[cell.class_key]
            xib = np.ascontiguousarray(lu_solve(factor, bi))
            bhat = np.ascontiguousarray(bt + trace_from_interior @ bi)
            dhat = np.ascontiguousarray(dt + di @ recovery)
            # ``recovery=-Vii^{-1}Vit``; hence ``Dt-Di*Xit=Dt+Di*recovery``.
            for row in range(nt):
                original = int(cell.trace_original_dofs[row])
                if original not in constraints.original_to_active:
                    if np.any(bt[row]) or np.any(dt[:, row]):
                        raise ValueError("local port coupling touches an MPC slave trace row")
            for values in (schur, recovery, trace_from_interior, bi, bt, di, dt, bhat, dhat, xib):
                if not np.isfinite(values).all():
                    raise ValueError("local p6 carrier data contains non-finite values")
            result.append(
                _CellActionData(
                    original_interiors=np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType).copy(),
                    original_trace=np.asarray(cell.trace_original_dofs, dtype=PETSc.IntType).copy(),
                    active_ids=np.asarray(active_ids, dtype=PETSc.IntType),
                    expansion=expansion,
                    class_key=cell.class_key,
                    S_V=schur,
                    recovery=recovery,
                    trace_from_interior=trace_from_interior,
                    interior_lu=factor,
                    Bi=_readonly(bi),
                    Bt=_readonly(bt),
                    Di=_readonly(di),
                    Dt=_readonly(dt),
                    ports=np.asarray(ports, dtype=PETSc.IntType),
                    Bhat=_readonly(bhat),
                    Dhat=_readonly(dhat),
                    XiB=_readonly(xib),
                    Hlocal=_readonly(h),
                )
            )
        return tuple(result)

    def _prepare_direct_terms(self) -> None:
        constraints = self.condensed.trace_constraints
        original_parts: dict[str, dict[int, list[np.ndarray]]] = {
            "B": defaultdict(list),
            "D": defaultdict(list),
        }
        original_values: dict[str, dict[int, list[np.ndarray]]] = {
            "B": defaultdict(list),
            "D": defaultdict(list),
        }
        active_parts: dict[str, dict[int, list[np.ndarray]]] = {
            "B": defaultdict(list),
            "D": defaultdict(list),
        }
        active_value_parts: dict[str, dict[int, list[np.ndarray]]] = {
            "B": defaultdict(list),
            "D": defaultdict(list),
        }
        for term in self._direct_terms:
            for side, rows, values in (
                ("B", term.B_original_rows, term.B_values),
                ("D", term.D_original_rows, term.D_values),
            ):
                if len(rows) == 0:
                    continue
                if any(int(original) not in constraints.original_to_active for original in rows):
                    raise ValueError(
                        f"direct {side} carrier contains an MPC slave or unknown trace row"
                    )
                # Carrier rows are already MPC-processed independent rows.
                # Keep one contiguous segment per port/side; do not create a
                # Python object (or one tiny ndarray) per nonzero entry.
                original_parts[side][term.port_index].append(rows.copy())
                original_values[side][term.port_index].append(values.copy())
                active_parts[side][term.port_index].append(
                    np.fromiter(
                        (constraints.original_to_active[int(original)] for original in rows),
                        dtype=PETSc.IntType,
                        count=len(rows),
                    )
                )
                active_value_parts[side][term.port_index].append(values.copy())
        for port in sorted(original_parts["B"]):
            self._direct_B_original[port] = (
                np.concatenate(original_parts["B"][port]),
                np.concatenate(original_values["B"][port]),
            )
        for port in sorted(original_parts["D"]):
            self._direct_D_original[port] = (
                np.concatenate(original_parts["D"][port]),
                np.concatenate(original_values["D"][port]),
            )
        for port in sorted(active_parts["B"]):
            self._direct_B_active[port] = (
                np.concatenate(active_parts["B"][port]),
                np.concatenate(active_value_parts["B"][port]),
            )
        for port in sorted(active_parts["D"]):
            self._direct_D_active[port] = (
                np.concatenate(active_parts["D"][port]),
                np.concatenate(active_value_parts["D"][port]),
            )

    @property
    def H_p(self) -> np.ndarray:
        """Borrow a readonly copy of the original carrier port block."""

        return self._H_p.copy()

    @property
    def Hhat(self) -> np.ndarray:
        """Return the small post-elimination port block."""

        return self._Hhat.copy()

    @property
    def audit(self) -> Mapping[str, Any]:
        self._audit["apply_count"] = int(self._apply_count)
        self._audit["hp_solve_count"] = int(self._hp_solve_count)
        return MappingProxyType(self._audit)

    @property
    def buffer_inventory(self) -> Mapping[str, Any]:
        """Return a compact proof that class payloads are shared by cells."""

        return MappingProxyType(
            {
                "cell_count": len(self._cells),
                "class_count": len({cell.class_key for cell in self._cells}),
                "unique_S_V_buffers": len({id(cell.S_V) for cell in self._cells}),
                "unique_recovery_buffers": len({id(cell.recovery) for cell in self._cells}),
                "unique_LU_factor_buffers": len({id(cell.interior_lu[0]) for cell in self._cells}),
                "unique_trace_rhs_projection_buffers": len(
                    {id(cell.trace_from_interior) for cell in self._cells}
                ),
                "local_carrier_cell_payload_bytes": int(
                    sum(
                        cell.Bi.nbytes
                        + cell.Bt.nbytes
                        + cell.Di.nbytes
                        + cell.Dt.nbytes
                        + cell.Bhat.nbytes
                        + cell.Dhat.nbytes
                        + cell.XiB.nbytes
                        + cell.Hlocal.nbytes
                        for cell in self._cells
                    )
                ),
            }
        )

    @property
    def cache_identity(self) -> Mapping[str, Any]:
        """Hash retained class arrays and the two small port blocks."""

        classes: dict[str, dict[str, str]] = {}
        for cell in self._cells:
            key = repr(cell.class_key)
            if key in classes:
                continue
            classes[key] = {
                "S_V_sha256": _array_sha256(cell.S_V),
                "recovery_sha256": _array_sha256(cell.recovery),
                "trace_rhs_projection_sha256": _array_sha256(cell.trace_from_interior),
                "LU_payload_sha256": _array_sha256(cell.interior_lu[0]),
            }
        return MappingProxyType(
            {
                "schema_version": "task039extra.v19.p6-cell-condensed-cache-identity.v1",
                "class_payloads": classes,
                "H_p_sha256": _array_sha256(self._H_p),
                "Hhat_sha256": _array_sha256(self._Hhat),
                "matrix_hash": None,
                "global_S6_matrix": False,
                "global_A6_matrix": False,
            }
        )

    @property
    def operator_recipe(self) -> Mapping[str, Any]:
        """Describe the action without pretending that an ``S6`` hash exists."""

        return MappingProxyType(
            {
                "schema_version": "task039extra.v19.p6-cell-condensed-recipe.v1",
                "formula": "S_V=Vtt-Vti*Vii^-1*Vit; Bhat=Bt-Vti*Vii^-1*Bi; Dhat=Dt-Di*Vii^-1*Vit; Hhat=Hp+Di*Vii^-1*Bi",
                "sign_convention": "augmented=[[V,B],[-D,Hp]]",
                "trace_action": "MPI1 NumPy gather expansion, owner-local S_V/Bhat/Dhat multiply, conjugate-transpose scatter",
                "port_action": "stream sparse direct trace terms plus dense Hhat only",
                "original_hp_for_bridge": True,
                "global_S6_matrix": False,
                "global_A6_matrix": False,
                "buffer_inventory": dict(self.buffer_inventory),
                "cache_identity": dict(self.cache_identity),
                "retained_class_keys": [repr(cell.class_key) for cell in self._cells],
            }
        )

    @property
    def reduced_size(self) -> int:
        return int(self.condensed.active_rows + self.condensed.appended_rows)

    @property
    def hp_solve_count(self) -> int:
        return int(self._hp_solve_count)

    def _check_reduced_array(self, value: Any, name: str) -> np.ndarray:
        return _complex_vector(value, name, size=self.reduced_size)

    def _apply_array(self, value: Any) -> np.ndarray:
        source = self._check_reduced_array(value, "reduced source")
        active = source[: self.condensed.active_rows]
        alpha = source[self.condensed.active_rows :]
        result = np.zeros_like(source)
        for cell in self._cells:
            local_trace = np.asarray(cell.expansion @ active[cell.active_ids], dtype=np.complex128).reshape(-1)
            local_action = cell.S_V @ local_trace
            if len(cell.ports):
                local_action = local_action + cell.Bhat @ alpha[cell.ports]
            result[cell.active_ids] += np.asarray(cell.expansion.conjugate().T @ local_action).reshape(-1)
            if len(cell.ports):
                result[self.condensed.active_rows + cell.ports] += -cell.Dhat @ local_trace
        result[self.condensed.active_rows :] += self._Hhat @ alpha
        self._add_direct_reduced(result, alpha, active)
        self._apply_count += 1
        return np.ascontiguousarray(result)

    def _add_direct_reduced(self, target: np.ndarray, alpha: np.ndarray, active: np.ndarray) -> None:
        for port, (rows, values) in self._direct_B_active.items():
            factor = alpha[port]
            np.add.at(target, rows, values * factor)
        for port, (rows, values) in self._direct_D_active.items():
            total = np.dot(values, active[rows])
            target[self.condensed.active_rows + port] -= total

    def mult(self, _matrix: PETSc.Mat | None, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """PETSc MatPython callback backed by the single validated action path."""

        if self._destroyed:
            raise RuntimeError("p6 cell-condensed action has been destroyed")
        if source.getSize() != self.reduced_size or target.getSize() != self.reduced_size:
            raise ValueError("p6 action vector has the wrong global size")
        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("PETSc p6 MatPython action is currently MPI1-only")
        source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        target_values = self._apply_array(source_values)
        target_array = target.getArray()
        if target_array.size != target_values.size:
            raise ValueError("p6 action vector has the wrong local size")
        target_array[:] = target_values

    def apply(self, source: Any) -> Any:
        """Apply to a NumPy reduced vector or return a new PETSc vector."""

        if isinstance(source, PETSc.Vec):
            result = source.duplicate()
            try:
                self.mult(self._matrix, source, result)
                return result
            except BaseException:
                result.destroy()
                raise
        if self._destroyed:
            raise RuntimeError("p6 cell-condensed action has been destroyed")
        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("NumPy p6 action vectors are MPI1-only; use the PETSc MatPython path")
        return self._apply_array(source)

    def create_matrix(self) -> PETSc.Mat:
        """Create a PETSc Python matrix shell; no AIJ payload is allocated."""

        if self._destroyed:
            raise RuntimeError("p6 cell-condensed action has been destroyed")
        if self._matrix is None:
            self._matrix = PETSc.Mat().createPython(
                ((self.condensed.owned_active_rows + self.condensed.owned_appended_rows, self.reduced_size),) * 2,
                context=self,
                comm=self.condensed.comm,
            )
            self._matrix.setUp()
        return self._matrix

    def original_hp_solve(self, rhs: Any) -> np.ndarray:
        """Solve with the original ``H_p`` (never with ``Hhat``)."""

        values = _complex_vector(rhs, "H_p RHS", size=self.condensed.appended_rows)
        result = np.ascontiguousarray(np.linalg.solve(self._H_p, values))
        if not np.isfinite(result).all():
            raise FloatingPointError("H_p solve returned non-finite values")
        self._hp_solve_count += 1
        return result

    def _full_array(self, value: Any | None, name: str) -> np.ndarray:
        if value is None:
            return np.zeros(self.condensed.full_rows, dtype=np.complex128)
        if isinstance(value, PETSc.Vec):
            if value.getSize() != self.condensed.full_rows:
                raise ValueError(f"{name} has the wrong global size")
            if self.condensed.comm.Get_size() != 1:
                raise NotImplementedError("full NumPy extraction is MPI1-only")
            return np.asarray(value.getValues(np.arange(self.condensed.full_rows, dtype=PETSc.IntType)), dtype=np.complex128)
        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("full NumPy vectors are MPI1-only")
        return _complex_vector(value, name, size=self.condensed.full_rows)

    def inject_trace_port(self, reduced_rhs: Any) -> np.ndarray:
        """Implement ``J^H``: inject active trace and port coordinates, zero i/slaves."""

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("global NumPy injection is MPI1-only; use a PETSc bridge adapter")
        value = self._check_reduced_array(reduced_rhs, "reduced injection")
        full = np.zeros(self.condensed.full_rows, dtype=np.complex128)
        active = value[: self.condensed.active_rows]
        for original in self.condensed.trace_constraints.owned_active_original_dofs:
            active_id = self.condensed.trace_constraints.original_to_active[int(original)]
            full[int(original)] = active[active_id]
        return full

    def _cell_internal_rhs(self, full: np.ndarray, cell: _CellActionData) -> np.ndarray:
        return np.asarray(full[cell.original_interiors], dtype=np.complex128)

    def reduce_rhs(
        self,
        full_rhs: Any,
        *,
        port_rhs: Any | None = None,
        rhs_is_mpc_dual: bool = False,
    ) -> np.ndarray:
        """Form ``(f_t,f_p)`` for arbitrary internal and port RHS values."""

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("global NumPy RHS reduction is MPI1-only")
        full = self._full_array(full_rhs, "full p6 RHS")
        result = np.zeros(self.reduced_size, dtype=np.complex128)
        constraints = self.condensed.trace_constraints
        if rhs_is_mpc_dual:
            slave_rows = [
                int(original)
                for original in self.condensed.owned_trace_original_dofs
                if int(original) not in constraints.original_to_active
            ]
            if slave_rows and np.any(full[np.asarray(slave_rows, dtype=np.int64)] != 0.0):
                raise ValueError("MPC-dual RHS has nonzero trace slave entries")
            for original in constraints.owned_active_original_dofs:
                active = constraints.original_to_active[int(original)]
                result[active] += full[int(original)]
        else:
            for original in self.condensed.owned_trace_original_dofs:
                ids, coefficients = constraints.expansion_by_original[int(original)]
                result[ids] += np.conjugate(coefficients) * full[int(original)]
        for cell in self._cells:
            bi = self._cell_internal_rhs(full, cell)
            if not np.any(bi):
                continue
            correction = cell.trace_from_interior @ bi
            for row, original in enumerate(cell.original_trace):
                ids, coefficients = constraints.expansion_by_original[int(original)]
                result[ids] += np.conjugate(coefficients) * correction[row]
            if len(cell.ports):
                result[self.condensed.active_rows + cell.ports] += cell.Di @ lu_solve(cell.interior_lu, bi)
        if port_rhs is not None:
            result[self.condensed.active_rows :] += _complex_vector(
                port_rhs, "port RHS", size=self.condensed.appended_rows
            )
        return result

    def recover_storage(
        self,
        reduced_solution: Any,
        *,
        full_rhs: Any | None = None,
        expand_trace: bool = False,
    ) -> np.ndarray:
        """Recover storage with exact slave zeros by default.

        Local trace values always use the constraint expansion internally.
        The returned storage keeps only independent trace entries unless
        ``expand_trace=True`` is explicitly requested for a physical
        post-processing copy.  Native actions and the BAL_H bridge therefore
        never silently perform MPC backsubstitution.
        """

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("global NumPy recovery is MPI1-only")
        value = self._check_reduced_array(reduced_solution, "reduced solution")
        full_rhs_values = self._full_array(full_rhs, "full recovery RHS")
        active = value[: self.condensed.active_rows]
        alpha = value[self.condensed.active_rows :]
        result = np.zeros(self.condensed.full_rows, dtype=np.complex128)
        constraints = self.condensed.trace_constraints
        trace_rows = (
            self.condensed.owned_trace_original_dofs
            if expand_trace
            else self.condensed.trace_constraints.owned_active_original_dofs
        )
        for original in trace_rows:
            ids, coefficients = constraints.expansion_by_original[int(original)]
            result[int(original)] = np.dot(coefficients, active[ids])
        for cell in self._cells:
            local_trace = np.asarray(cell.expansion @ active[cell.active_ids], dtype=np.complex128).reshape(-1)
            bi = self._cell_internal_rhs(full_rhs_values, cell)
            values = lu_solve(cell.interior_lu, bi) + cell.recovery @ local_trace
            if len(cell.ports):
                values = values - cell.XiB @ alpha[cell.ports]
            result[cell.original_interiors] = values
        if not np.isfinite(result).all():
            raise FloatingPointError("p6 local recovery returned non-finite values")
        return result

    def evaluate_native_residual(
        self,
        reduced_solution: Any,
        full_rhs: Any,
        native_apply: Callable[[np.ndarray], Any],
        *,
        port_rhs: Any | None = None,
        rhs_is_mpc_dual: bool = True,
        reduced_residual: Any | None = None,
    ) -> dict[str, Any]:
        """Evaluate native and augmented residuals from one reduced iterate.

        ``native_apply`` is the existing full p6 ``A6`` action.  This helper
        owns the bookkeeping used by the runner: strict-zero storage recovery,
        the original residual, the augmented port residual, local internal
        residuals, reduced Schur residual injection, and the independent
        ``e_FE-B H_p^{-1}e_p`` identity.  No reference solution or reference
        action is involved.
        """

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("native residual evaluation currently exposes a global NumPy API only for MPI1")
        solution = self._check_reduced_array(reduced_solution, "reduced solution")
        rhs = self._full_array(full_rhs, "full p6 RHS")
        ports_rhs = (
            np.zeros(self.condensed.appended_rows, dtype=np.complex128)
            if port_rhs is None
            else _complex_vector(port_rhs, "port RHS", size=self.condensed.appended_rows)
        )
        field = self.recover_storage(solution, full_rhs=rhs, expand_trace=False)
        native_output = native_apply(field)
        native_output = self._full_array(native_output, "native A6 output")
        alpha = solution[self.condensed.active_rows :]
        hp_inverse_port_rhs = self.original_hp_solve(ports_rhs)
        native_effective_rhs = rhs - self.apply_B_full(hp_inverse_port_rhs)
        native_residual = native_effective_rhs - native_output
        port_action = self.apply_D_full(field)
        augmented_port_residual = ports_rhs + port_action - self._H_p @ alpha
        reduced_rhs = self.reduce_rhs(
            rhs,
            port_rhs=ports_rhs,
            rhs_is_mpc_dual=rhs_is_mpc_dual,
        )
        if reduced_residual is None:
            schur_action = self._apply_array(solution)
            schur_residual = reduced_rhs - schur_action
        else:
            schur_residual = _complex_vector(
                reduced_residual,
                "supplied reduced residual",
                size=self.reduced_size,
            )
            schur_action = reduced_rhs - schur_residual
        schur_injection = self.inject_trace_port(schur_residual)

        internal_residuals: list[np.ndarray] = []
        internal_scales: list[float] = []
        port_internal_correction = np.zeros(self.condensed.appended_rows, dtype=np.complex128)
        trace_internal_correction = np.zeros(self.condensed.active_rows, dtype=np.complex128)
        for cell in self._cells:
            local_trace = np.asarray(
                cell.expansion @ solution[: self.condensed.active_rows][cell.active_ids],
                dtype=np.complex128,
            ).reshape(-1)
            internal = field[cell.original_interiors]
            rhs_i = rhs[cell.original_interiors]
            vii_xi = _factored_matrix_action(cell.interior_lu, internal)
            vit_xt = -_factored_matrix_action(cell.interior_lu, cell.recovery @ local_trace)
            bi_alpha = (
                cell.Bi @ alpha[cell.ports]
                if len(cell.ports)
                else np.zeros_like(rhs_i)
            )
            lhs_i = vii_xi + vit_xt + bi_alpha
            internal_error = rhs_i - lhs_i
            internal_residuals.append(internal_error)
            trace_correction = cell.trace_from_interior @ internal_error
            for row, original in enumerate(cell.original_trace):
                ids, coefficients = self.condensed.trace_constraints.expansion_by_original[int(original)]
                trace_internal_correction[ids] += np.conjugate(coefficients) * trace_correction[row]
            if len(cell.ports):
                port_internal_correction[cell.ports] += cell.Di @ lu_solve(
                    cell.interior_lu,
                    internal_error,
                )
            internal_scales.append(
                max(
                    float(np.linalg.norm(vii_xi))
                    + float(np.linalg.norm(vit_xt))
                    + float(np.linalg.norm(bi_alpha))
                    + float(np.linalg.norm(rhs_i)),
                    0.0,
                )
            )
        internal_residual = (
            np.concatenate(internal_residuals)
            if internal_residuals
            else np.empty(0, dtype=np.complex128)
        )
        internal_operation_scale = float(sum(internal_scales))
        # Build e_FE from the independently formed Schur and internal
        # residuals.  In particular, do not infer it from A6 alone: that
        # would make the native-vs-augmented identity circular.
        trace_residual = schur_residual[: self.condensed.active_rows] - trace_internal_correction
        augmented_fe_residual = self.inject_trace_port(
            np.r_[trace_residual, np.zeros(self.condensed.appended_rows, dtype=np.complex128)]
        )
        for cell, internal_error in zip(self._cells, internal_residuals, strict=True):
            augmented_fe_residual[cell.original_interiors] = internal_error
        hp_inverse_Dx = self.original_hp_solve(port_action)
        hp_inverse_port_residual = self.original_hp_solve(augmented_port_residual)
        B_hp_inverse_port_residual = self.apply_B_full(hp_inverse_port_residual)
        derived_native_residual = augmented_fe_residual - B_hp_inverse_port_residual
        identity_difference = native_residual - derived_native_residual
        native_scale = float(np.linalg.norm(native_effective_rhs))
        port_scale = (
            float(np.linalg.norm(port_action))
            + float(np.linalg.norm(self._H_p @ alpha))
            + float(np.linalg.norm(ports_rhs))
        )
        schur_operation_scale = float(
            np.linalg.norm(reduced_rhs) + np.linalg.norm(schur_action)
        )
        port_schur_error = schur_residual[self.condensed.active_rows :] - (
            augmented_port_residual + port_internal_correction
        )
        identity_operation_scale = float(
            np.linalg.norm(native_effective_rhs)
            + np.linalg.norm(native_output)
            + np.linalg.norm(augmented_fe_residual)
            + np.linalg.norm(B_hp_inverse_port_residual)
        )
        return {
            "storage_solution": field,
            "native_effective_rhs": native_effective_rhs,
            "native_residual": native_residual,
            "augmented_fe_residual": augmented_fe_residual,
            "augmented_port_residual": augmented_port_residual,
            "internal_residual": internal_residual,
            "schur_residual": schur_residual,
            "schur_residual_injection": schur_injection,
            "schur_port_residual": schur_residual[self.condensed.active_rows :],
            "port_internal_correction": port_internal_correction,
            "schur_port_identity_difference": port_schur_error,
            "derived_native_residual": derived_native_residual,
            "native_identity_difference": identity_difference,
            "hp_inverse_Dx": hp_inverse_Dx,
            "retained_alpha": alpha.copy(),
            "native_residual_relative": _operation_relative(np.linalg.norm(native_residual), native_scale),
            "port_residual_relative": _operation_relative(np.linalg.norm(augmented_port_residual), port_scale),
            "internal_residual_relative": _operation_relative(
                np.linalg.norm(internal_residual), internal_operation_scale
            ),
            "schur_residual_relative": _operation_relative(
                np.linalg.norm(schur_residual), schur_operation_scale
            ),
            "native_identity_relative": _operation_relative(
                np.linalg.norm(identity_difference), identity_operation_scale
            ),
            "schur_port_identity_relative": _operation_relative(
                np.linalg.norm(port_schur_error),
                port_scale,
            ),
            "native_rhs_norm": float(np.linalg.norm(rhs)),
            "port_action_norm": float(np.linalg.norm(port_action)),
            "port_hp_solution_norm": float(np.linalg.norm(self._H_p @ alpha)),
            "hp_solve_count": int(self._hp_solve_count),
            "native_identity_formula": "e_FE-B*H_p^{-1}*e_p",
            "strict_zero_slave_storage": True,
            "rhs_is_mpc_dual": bool(rhs_is_mpc_dual),
            "reduced_residual_supplied": reduced_residual is not None,
            "hp_inverse_port_rhs": hp_inverse_port_rhs,
            "hp_inverse_port_residual": hp_inverse_port_residual,
            "native_rhs_operation_scale": native_scale,
            "port_operation_scale": port_scale,
            "internal_operation_scale": internal_operation_scale,
            "schur_operation_scale": schur_operation_scale,
            "schur_port_identity_operation_scale": port_scale,
            "native_identity_operation_scale": identity_operation_scale,
        }

    def apply_B_full(self, alpha: Any) -> np.ndarray:
        """Apply the original full-storage ``B`` coupling, without ``Hhat``."""

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("global NumPy B action is MPI1-only")
        values = _complex_vector(alpha, "port values", size=self.condensed.appended_rows)
        result = np.zeros(self.condensed.full_rows, dtype=np.complex128)
        constraints = self.condensed.trace_constraints
        for cell in self._cells:
            if not len(cell.ports):
                continue
            local = values[cell.ports]
            result[cell.original_interiors] += cell.Bi @ local
            for row, original in enumerate(cell.original_trace):
                if int(original) in constraints.original_to_active:
                    result[int(original)] += cell.Bt[row] @ local
        for port, (rows, row_values) in self._direct_B_original.items():
            result[rows] += row_values * values[port]
        return result

    def apply_D_full(self, full_field: Any) -> np.ndarray:
        """Apply the original full-storage ``D`` coupling."""

        if self.condensed.comm.Get_size() != 1:
            raise NotImplementedError("global NumPy D action is MPI1-only")
        field = self._full_array(full_field, "full p6 field")
        result = np.zeros(self.condensed.appended_rows, dtype=np.complex128)
        constraints = self.condensed.trace_constraints
        for cell in self._cells:
            if not len(cell.ports):
                continue
            local = cell.Di @ field[cell.original_interiors]
            trace = field[cell.original_trace].copy()
            for row, original in enumerate(cell.original_trace):
                if int(original) not in constraints.original_to_active:
                    trace[row] = 0.0
            local += cell.Dt @ trace
            result[cell.ports] += local
        for port, (rows, row_values) in self._direct_D_original.items():
            result[port] += np.dot(row_values, field[rows])
        return result

    def create_reduced_rhs_vector(self) -> PETSc.Vec:
        """Create a PETSc vector with the action's reduced layout."""

        return self.condensed.create_augmented_vector()

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        matrix = self._matrix
        self._matrix = None
        self._destroyed = True
        if matrix is not None and _matrix is None:
            matrix.destroy()
        if self.owns_condensed:
            self.condensed.destroy()


def build_p6_cell_condensed_action_from_carrier(
    condensed: AssemblyTimeCondensedSystem,
    carrier: Any,
    *,
    H_p: Any | None = None,
    owns_condensed: bool = False,
) -> P6CellCondensedAction:
    """Translate a native carrier into local/internal and direct trace terms.

    Carrier ``coupling_rows`` are the ``B`` rows and ``projection_rows`` are
    the ``D`` rows, matching the already-qualified V18 interface.  Interior
    rows become local ``Bi``/``Di``; independent trace rows remain sparse
    direct entries.  A carrier row that is an MPC slave is rejected, so the
    Floquet pullback cannot be applied twice.
    """

    entries = tuple(getattr(carrier, "entries", ()))
    if len(entries) != condensed.appended_rows:
        raise ValueError("carrier entry count differs from appended port rows")
    if H_p is None:
        hp = np.zeros((condensed.appended_rows, condensed.appended_rows), dtype=np.complex128)
        for port, entry in enumerate(entries):
            hp[port, port] = complex(getattr(entry, "normalization_h"))
    else:
        hp = _complex_matrix(H_p, "H_p", shape=(condensed.appended_rows, condensed.appended_rows))
    interior_locations: dict[int, tuple[int, int]] = {}
    for index, cell in enumerate(condensed.cell_recovery_maps):
        for local, original in enumerate(cell.interior_original_dofs):
            original = int(original)
            if original in interior_locations:
                raise ValueError(f"interior original DoF {original} belongs to multiple cells")
            interior_locations[original] = (index, local)
    constraints = condensed.trace_constraints
    bi_by_cell: dict[int, dict[int, dict[int, complex]]] = defaultdict(lambda: defaultdict(dict))
    di_by_cell: dict[int, dict[int, dict[int, complex]]] = defaultdict(lambda: defaultdict(dict))
    direct: list[P6DirectTracePortTerms] = []

    def consume(rows: Any, values: Any, port: int, target: dict[int, dict[int, dict[int, complex]]] | None, side: str) -> tuple[np.ndarray, np.ndarray]:
        row_array = np.asarray(rows, dtype=np.int64).reshape(-1)
        value_array = _complex_vector(values, f"carrier {side} values", size=len(row_array))
        original_rows: list[int] = []
        original_values: list[complex] = []
        for row, value in zip(row_array, value_array, strict=True):
            row = int(row)
            location = interior_locations.get(row)
            if location is not None:
                if target is None:
                    raise RuntimeError("internal carrier target is missing")
                cell_index, local = location
                target[cell_index][port][local] = target[cell_index][port].get(local, 0.0) + complex(value)
            else:
                if row not in constraints.original_to_active:
                    raise ValueError("carrier includes an MPC slave or unknown trace row")
                original_rows.append(row)
                original_values.append(complex(value))
        return (
            np.asarray(original_rows, dtype=PETSc.IntType),
            np.asarray(original_values, dtype=np.complex128),
        )

    for port, entry in enumerate(entries):
        b_rows, b_values = consume(getattr(entry, "coupling_rows"), getattr(entry, "coupling_values"), port, bi_by_cell, "B")
        d_rows, d_values = consume(getattr(entry, "projection_rows"), getattr(entry, "projection_values"), port, di_by_cell, "D")
        direct.append(P6DirectTracePortTerms(port, b_rows, b_values, d_rows, d_values))

    terms: dict[int, P6CellPortTerms] = {}
    for cell_index in sorted(set(bi_by_cell) | set(di_by_cell)):
        cell = condensed.cell_recovery_maps[cell_index]
        ports = np.asarray(sorted(set(bi_by_cell[cell_index]) | set(di_by_cell[cell_index])), dtype=PETSc.IntType)
        ni = len(cell.interior_original_dofs)
        bi = np.zeros((ni, len(ports)), dtype=np.complex128)
        di = np.zeros((len(ports), ni), dtype=np.complex128)
        for local_port, port in enumerate(ports):
            for local, value in bi_by_cell[cell_index].get(int(port), {}).items():
                bi[local, local_port] = value
            for local, value in di_by_cell[cell_index].get(int(port), {}).items():
                di[local_port, local] = value
        terms[cell_index] = P6CellPortTerms(bi, di, ports)
    return P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms=terms,
        direct_trace_terms=direct,
        owns_condensed=owns_condensed,
    )


class P6RetainedBALHBridge:
    """Implement ``J M_aug J^H`` around one retained BAL_H callback."""

    def __init__(self, action: P6CellCondensedAction, bal_h: Callable[[np.ndarray], Any]) -> None:
        if not callable(bal_h):
            raise TypeError("BAL_H bridge must be callable")
        self.action = action
        self._bal_h = bal_h
        self.apply_count = 0
        self.bal_h_count = 0

    def apply(self, rhs: Any) -> np.ndarray:
        """Apply the retained-space bridge using the original ``H_p`` solve."""

        if self.action.condensed.comm.Get_size() != 1:
            raise NotImplementedError("the retained BAL_H bridge currently exposes a global NumPy API only for MPI1")
        value = self.action._check_reduced_array(rhs, "BAL_H bridge RHS")
        if not np.any(value):
            # J M_aug J^H is linear and maps zero to zero.  Avoid entering
            # the expensive retained BAL_H callback for this exact case.
            self.apply_count += 1
            return np.zeros_like(value)
        port_rhs = value[self.action.condensed.active_rows :]
        full_rhs = self.action.inject_trace_port(value)
        hp_inverse_port_rhs = self.action.original_hp_solve(port_rhs)
        w = full_rhs - self.action.apply_B_full(hp_inverse_port_rhs)
        z = self._bal_h(w)
        z_values = self.action._full_array(z, "BAL_H output")
        self.bal_h_count += 1
        alpha = self.action.original_hp_solve(port_rhs + self.action.apply_D_full(z_values))
        output = np.concatenate(
            (
                z_values[np.asarray(self.action.condensed.trace_constraints.owned_active_original_dofs, dtype=np.int64)],
                alpha,
            )
        )
        if output.shape != value.shape or not np.isfinite(output).all():
            raise FloatingPointError("J M_aug J^H returned an invalid vector")
        self.apply_count += 1
        return output


def native_residual_from_augmented(
    action: P6CellCondensedAction,
    top_residual: Any,
    port_residual: Any,
) -> np.ndarray:
    """Evaluate ``e_FE - B H_p^{-1} e_p`` with the original carrier block."""

    top = _complex_vector(top_residual, "top augmented residual", size=action.condensed.full_rows)
    port = _complex_vector(port_residual, "port augmented residual", size=action.condensed.appended_rows)
    return top - action.apply_B_full(action.original_hp_solve(port))


__all__ = (
    "CondensedPhysicalCell",
    "P6CellCondensedAction",
    "P6CellPortTerms",
    "P6DirectTracePortTerms",
    "P6RetainedBALHBridge",
    "build_p6_cell_condensed_action_from_carrier",
    "condense_physical_cell_blocks",
    "native_residual_from_augmented",
)
