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
from .original_port_blocks import (
    DenseOriginalPortBlock,
    DiagonalOriginalPortBlock,
)
from .retained_port_block_layout import (
    LEGACY_PORT_LAYOUT,
    RESEARCH_PORT_LAYOUT,
    build_cached_port_representation,
    port_block_representation_identity,
)


P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES = 32 * 1024


def _unique_numpy_backing_inventory(values: Sequence[np.ndarray]) -> tuple[int, int]:
    owners: dict[int, int] = {}
    for value in values:
        owner = value
        while isinstance(getattr(owner, "base", None), np.ndarray):
            owner = owner.base
        owners[id(owner)] = int(owner.nbytes)
    return len(owners), int(sum(owners.values()))


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
class P6MatrixFreeHhatTerm:
    """One local, action-only contribution to ``Hhat @ alpha``.

    ``interior_rhs`` is the already formed local ``Bi @ alpha`` vector for
    this call. ``apply_Di`` must return the *raw* local ``Di @ x`` values in
    ``output_ports`` order; it must not divide by the original ``H_p`` or
    infer ``D`` from ``B``. The callback may use a bounded quadrature/action
    implementation instead of retaining a dense ``Di`` matrix.
    """

    output_ports: np.ndarray
    interior_lu: tuple[np.ndarray, np.ndarray]
    interior_rhs: np.ndarray
    apply_Di: Callable[[np.ndarray], Any]
    callback_workspace_bytes: int = 0


def raw_plane_D_action_from_global_normalized(
    global_normalized_action: Any,
    modes: Sequence[Any],
    cfg: Any,
    original_h: DiagonalOriginalPortBlock,
) -> np.ndarray:
    """Convert S5-style ``D_global/H_global`` values to raw plane ``D``.

    ``FullspaceDtnAction.recover_auxiliary`` and the V11 q60 helper return
    normalized modal values. The P6 carrier factory instead stores raw
    ``projection_values`` as ``Di`` and keeps plane ``normalization_h`` in
    the original ``H_p`` block. Convert the normalized global-z value to the
    boundary-plane modal coordinate with the production gauge routine, then
    apply that same plane ``H_p``. This returns raw ``Di @ x`` values and
    deliberately performs no ``B`` conjugacy inference.
    """

    if not isinstance(original_h, DiagonalOriginalPortBlock):
        raise TypeError("normalized projection conversion requires the explicit diagonal plane H_p block")
    values = np.asarray(global_normalized_action)
    mode_rows = tuple(modes)
    if (
        values.ndim not in (1, 2)
        or values.shape[0] != original_h.count
        or values.dtype != np.dtype(np.complex128)
        or not values.flags.c_contiguous
        or not np.isfinite(values).all()
        or len(mode_rows) != original_h.count
    ):
        raise ValueError("global normalized D action and ordered mode rows have incompatible layouts")
    for key, mode in zip(original_h.mode_keys, mode_rows, strict=True):
        if tuple(key[1:]) != (
            str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)
        ):
            raise ValueError("plane H_p keys differ from the normalized D mode ordering")
    from .dtn_boundary_phase_gauge import BOUNDARY_PLANE, solver_amplitudes_from_global

    plane_normalized = solver_amplitudes_from_global(
        values, mode_rows, cfg, BOUNDARY_PLANE
    )
    raw_action = np.asarray(original_h.apply(plane_normalized))
    if (
        raw_action.shape != values.shape
        or raw_action.dtype != np.dtype(np.complex128)
        or not raw_action.flags.c_contiguous
        or not np.isfinite(raw_action).all()
    ):
        raise FloatingPointError("boundary-plane raw Di action is nonfinite or has an invalid layout")
    return raw_action


def apply_p6_hhat_vector_action(
    original_h: DiagonalOriginalPortBlock | DenseOriginalPortBlock,
    amplitudes: Any,
    terms: Sequence[P6MatrixFreeHhatTerm],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> np.ndarray:
    """Apply ``H_p + sum(D_i V_ii^{-1} B_i)`` without storing ``Hhat``.

    Each term supplies its actual local ``B_i @ amplitudes`` vector and a
    callback for the independent raw ``D_i`` action. The original ``H_p``
    action comes from the validated port-block object. This supports a
    bounded subset or the complete ordered mode vector, and one or multiple
    right-hand sides, without allocating a mode-square matrix or a global
    factorization.
    """

    if not isinstance(original_h, (DiagonalOriginalPortBlock, DenseOriginalPortBlock)):
        raise TypeError("matrix-free Hhat action requires an explicit original H_p block")
    if not callable(allocation_gate):
        raise TypeError("matrix-free Hhat action requires a whole-tree allocation gate")
    alpha = np.asarray(amplitudes)
    if (
        alpha.ndim not in (1, 2)
        or alpha.shape[0] != original_h.count
        or (alpha.ndim == 2 and alpha.shape[1] == 0)
        or alpha.dtype != np.dtype(np.complex128)
        or not alpha.flags.c_contiguous
        or not np.isfinite(alpha).all()
    ):
        raise ValueError("Hhat amplitudes must be finite, C-contiguous complex128 with a complete port row")
    rhs_count = 1 if alpha.ndim == 1 else int(alpha.shape[1])
    result_bytes = int(alpha.size * np.dtype(np.complex128).itemsize)
    allocation_gate("p6_hhat_vector/original_H", {
        "matrix_payload_bytes": result_bytes,
        "workspace_bytes": result_bytes,
        "original_H_output_bytes": result_bytes,
        "allocation_semantics": "additional_objects_to_current_resident_RSS",
        "full_Hhat_allocated": False,
        "mode_square_matrix_allocated": False,
        "global_factorization_calls": 0,
    })
    result = np.asarray(original_h.apply(alpha))
    if (
        result.shape != alpha.shape
        or result.dtype != np.dtype(np.complex128)
        or not result.flags.c_contiguous
        or not np.isfinite(result).all()
    ):
        raise ValueError("original H_p action returned an invalid complex128 port vector")

    for index, term in enumerate(terms):
        if not isinstance(term, P6MatrixFreeHhatTerm):
            raise TypeError("matrix-free Hhat terms have an invalid type")
        ports = np.asarray(term.output_ports)
        if (
            ports.ndim != 1
            or ports.dtype.kind not in "iu"
            or not ports.size
            or (ports.size and (int(ports.min()) < 0 or int(ports.max()) >= original_h.count))
            or len(np.unique(ports)) != len(ports)
        ):
            raise ValueError("matrix-free Hhat output ports must be unique valid port indices")
        if not callable(term.apply_Di):
            raise TypeError("matrix-free Hhat term requires an independent Di action callback")
        if (
            isinstance(term.callback_workspace_bytes, bool)
            or not isinstance(term.callback_workspace_bytes, int)
            or term.callback_workspace_bytes < 0
        ):
            raise ValueError("matrix-free Hhat callback workspace must be a nonnegative integer")
        interior_rhs = np.asarray(term.interior_rhs)
        if (
            interior_rhs.ndim not in (1, 2)
            or interior_rhs.dtype != np.dtype(np.complex128)
            or not interior_rhs.flags.c_contiguous
            or not np.isfinite(interior_rhs).all()
            or (interior_rhs.ndim != alpha.ndim)
            or (interior_rhs.ndim == 2 and interior_rhs.shape[1] != rhs_count)
        ):
            raise ValueError("matrix-free Hhat internal RHS must match the finite complex128 input RHS layout")
        factor = term.interior_lu
        if not isinstance(factor, tuple) or len(factor) != 2:
            raise ValueError("matrix-free Hhat term requires a SciPy local LU factor")
        lu = np.asarray(factor[0])
        pivots = np.asarray(factor[1])
        interior_rows = int(interior_rhs.shape[0])
        if (
            interior_rows <= 0
            or lu.shape != (interior_rows, interior_rows)
            or lu.dtype != np.dtype(np.complex128)
            or not np.isfinite(lu).all()
            or pivots.shape != (interior_rows,)
            or pivots.dtype.kind not in "iu"
            or (pivots.size and (int(pivots.min()) < 0 or int(pivots.max()) >= interior_rows))
        ):
            raise ValueError("matrix-free Hhat local LU dimensions or values are invalid")

        solve_bytes = int(interior_rhs.size * np.dtype(np.complex128).itemsize)
        d_output_bytes = int(ports.size * rhs_count * np.dtype(np.complex128).itemsize)
        # Count the retained H_p output, LU solve result plus one solve-sized
        # work allowance, D output, indexed scatter scratch, and the caller's
        # declared peak callback workspace before either local allocation.
        scatter_workspace_bytes = int(d_output_bytes + ports.size * np.dtype(np.int64).itemsize)
        allocation_gate(f"p6_hhat_vector/local_D/{index}", {
            "matrix_payload_bytes": d_output_bytes,
            "workspace_bytes": (
                result_bytes + 2 * solve_bytes + scatter_workspace_bytes
                + int(term.callback_workspace_bytes)
            ),
            "original_H_output_bytes": result_bytes,
            "interior_solve_output_bytes": solve_bytes,
            "interior_solve_workspace_bytes": solve_bytes,
            "Di_output_bytes": d_output_bytes,
            "indexed_scatter_workspace_bytes": scatter_workspace_bytes,
            "callback_workspace_bytes": int(term.callback_workspace_bytes),
            "allocation_semantics": "additional_objects_to_current_resident_RSS",
            "full_Hhat_allocated": False,
            "mode_square_matrix_allocated": False,
            "global_factorization_calls": 0,
            "consumer_must_release_before_next": True,
        })
        interior_solution = np.ascontiguousarray(
            lu_solve(factor, interior_rhs, check_finite=True), dtype=np.complex128
        )
        if not np.isfinite(interior_solution).all():
            raise FloatingPointError("matrix-free Hhat local interior solve returned nonfinite values")
        interior_solution.flags.writeable = False
        di_action = term.apply_Di(interior_solution)
        di_action = np.asarray(di_action)
        expected_shape = (len(ports),) if alpha.ndim == 1 else (len(ports), rhs_count)
        if (
            di_action.shape != expected_shape
            or di_action.dtype != np.dtype(np.complex128)
            or not di_action.flags.c_contiguous
            or not np.isfinite(di_action).all()
        ):
            raise ValueError("independent Di callback returned an invalid raw port action")
        with np.errstate(over="ignore", invalid="ignore"):
            np.add.at(result, ports, di_action)
        if not np.isfinite(result).all():
            raise FloatingPointError("matrix-free Hhat accumulation returned nonfinite values")
        del interior_solution, di_action

    return result


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
    Bhat: np.ndarray | None
    Dhat: np.ndarray | None
    XiB: np.ndarray | None
    Hlocal: np.ndarray | None


def _normalise_port_terms(
    term: P6CellPortTerms | None,
    *,
    ni: int,
    nt: int,
    appended_rows: int,
    name: str,
    streamed: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
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
    h = (
        None
        if streamed and term.H is None
        else np.zeros((np_, np_), dtype=np.complex128)
        if term.H is None
        else _complex_matrix(term.H, f"{name}.H", shape=(np_, np_))
    )
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
        H_p: Any | None,
        port_terms: Mapping[int, P6CellPortTerms] | None = None,
        direct_trace_terms: Sequence[P6DirectTracePortTerms] = (),
        direct_terms_are_owned: bool = False,
        owns_condensed: bool = False,
        port_coupling_mode: str = "cached",
        port_block_layout: str = LEGACY_PORT_LAYOUT,
        original_port_block: Any | None = None,
    ) -> None:
        if condensed.matrix is not None:
            raise ValueError("p6 action-only condensation cannot borrow a materialized matrix")
        retained = condensed.retained_local_schur_by_class
        if retained is None:
            raise ValueError("p6 action-only condensation requires retained local Schur classes")
        if port_coupling_mode not in {"cached", "streamed"}:
            raise ValueError("port_coupling_mode must be 'cached' or 'streamed'")
        if port_block_layout not in {LEGACY_PORT_LAYOUT, RESEARCH_PORT_LAYOUT}:
            raise ValueError("unknown original/condensed port-block layout")
        if port_block_layout == RESEARCH_PORT_LAYOUT and port_coupling_mode != "cached":
            raise ValueError("cached representation requires cached local XiB data")
        self.port_block_layout = str(port_block_layout)
        self.port_coupling_mode = str(port_coupling_mode)
        self.condensed = condensed
        self.owns_condensed = bool(owns_condensed)
        self._streamed_action_lu_solve_count = 0
        self._streamed_recovery_lu_solve_count = 0
        self._streamed_hhat_lu_solve_count = 0
        self._streamed_max_local_scratch_bytes = 0
        # Hlocal contributions are merged into this original carrier block
        # below.  Own the copy explicitly so construction never mutates the
        # caller's carrier array; the large class payloads remain borrowed.
        self._original_port_block = None
        self._condensed_port_block = None
        if self.port_block_layout == LEGACY_PORT_LAYOUT:
            if H_p is None or original_port_block is not None:
                raise ValueError("legacy layout requires dense H_p and no original_port_block")
            self._H_p = np.array(_complex_matrix(H_p, "H_p"), dtype=np.complex128, copy=True, order="C")
            if self._H_p.shape != (condensed.appended_rows, condensed.appended_rows):
                raise ValueError("H_p shape differs from the appended port block")
        else:
            if H_p is not None or not isinstance(
                original_port_block, (DiagonalOriginalPortBlock, DenseOriginalPortBlock)
            ):
                raise ValueError("research layout requires an explicit diagonal/dense original_port_block and H_p=None")
            if original_port_block.count != condensed.appended_rows:
                raise ValueError("original_port_block size differs from the appended port rows")
            self._H_p = None
            self._original_port_block = original_port_block
        self._port_terms = dict(port_terms or {})
        unknown_cells = set(self._port_terms).difference(range(len(condensed.cell_recovery_maps)))
        if unknown_cells:
            raise ValueError(f"port terms refer to unknown cells: {sorted(unknown_cells)}")
        self._cells: tuple[_CellActionData, ...] = self._build_cells(retained)
        # The streamed prototype does not retain its staging map after cell
        # arrays are validated.  Preserve the established cached object's
        # metadata lifetime and behavior.
        if self.port_coupling_mode == "streamed":
            self._port_terms.clear()
        # Optional local H blocks are direct contributions to the original
        # carrier block.  Merge them before freezing H_p so that both the
        # native A6 action and the BAL_H bridge use the same original block;
        # Hhat then receives only the internal-elimination correction.
        for cell in self._cells:
            if len(cell.ports) and cell.Hlocal is not None:
                if self._H_p is None:
                    # The opt-in representation helper admits only absent or
                    # exactly-zero Hlocal; it must never silently drop a term.
                    if np.any(cell.Hlocal != 0):
                        raise NotImplementedError(
                            "research original-H representation does not admit nonzero Hlocal"
                        )
                else:
                    self._H_p[np.ix_(cell.ports, cell.ports)] += cell.Hlocal
        self._direct_terms = tuple(
            term
            if direct_terms_are_owned
            else _as_direct_term(term, condensed.appended_rows)
            for term in direct_trace_terms
        )
        self._direct_terms_are_owned = bool(direct_terms_are_owned)
        self._direct_B_original: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_D_original: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_B_active: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._direct_D_active: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._prepare_direct_terms()
        self._direct_terms = ()
        direct_output_arrays = [
            value
            for mapping in (
                self._direct_B_original,
                self._direct_D_original,
                self._direct_B_active,
                self._direct_D_active,
            )
            for pair in mapping.values()
            for value in pair
        ]
        direct_output_storage_count, direct_output_backing_bytes = (
            _unique_numpy_backing_inventory(direct_output_arrays)
        )
        if self.port_block_layout == RESEARCH_PORT_LAYOUT:
            self._original_port_block, self._condensed_port_block = build_cached_port_representation(
                self._original_port_block, self._cells
            )
            self._Hhat = None
        elif self.port_coupling_mode == "cached":
            self._Hhat = self._H_p.copy()
            for cell in self._cells:
                if len(cell.ports):
                    assert cell.XiB is not None
                    self._Hhat[np.ix_(cell.ports, cell.ports)] += cell.Di @ cell.XiB
            self._Hhat = _readonly(self._Hhat)
        else:
            self._Hhat = None
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
            "port_block_layout": self.port_block_layout,
            "Hhat_is_retained_small_dense_block": (
                self.port_coupling_mode == "cached" and self.port_block_layout == LEGACY_PORT_LAYOUT
            ),
            "Hhat_is_resident": (
                self.port_coupling_mode == "cached" and self.port_block_layout == LEGACY_PORT_LAYOUT
            ),
            "port_coupling_mode": self.port_coupling_mode,
            "shared_S_V_buffer_count": len({id(cell.S_V) for cell in self._cells}),
            "shared_recovery_buffer_count": len({id(cell.recovery) for cell in self._cells}),
            "shared_LU_factor_buffer_count": len({id(cell.interior_lu[0]) for cell in self._cells}),
            "class_cache_shared_across_cells": True,
            "direct_trace_B_entry_count": int(sum(len(rows) for rows, _values in self._direct_B_original.values())),
            "direct_trace_D_entry_count": int(sum(len(rows) for rows, _values in self._direct_D_original.values())),
            "direct_term_construction": {
                "strategy": (
                    "bounded_reusable_chunk_owned_outputs"
                    if self._direct_terms_are_owned
                    else "normalized_parts_and_concatenate"
                ),
                "chunk_entries": (
                    P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES
                    if self._direct_terms_are_owned
                    else None
                ),
                "reusable_chunk_payload_bytes": (
                    P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES
                    * (
                        np.dtype(np.int64).itemsize
                        + np.dtype(np.complex128).itemsize
                        + np.dtype(np.bool_).itemsize
                    )
                    if self._direct_terms_are_owned
                    else None
                ),
                "owned_original_arrays_transferred": self._direct_terms_are_owned,
                "unique_output_backing_storage_count": int(
                    direct_output_storage_count
                ),
                "unique_output_backing_bytes": int(direct_output_backing_bytes),
            },
            "apply_count": 0,
            "hp_solve_count": 0,
            "streamed_action_lu_solve_count": 0,
            "streamed_recovery_lu_solve_count": 0,
            "streamed_hhat_lu_solve_count": 0,
            "streamed_max_local_scratch_bytes": 0,
            "streamed_scratch_scope": (
                "maximum sum of named per-cell NumPy intermediates live in one "
                "streamed apply or recovery, plus the H_p action vector; excludes "
                "input/output vectors, shared resident payloads, and NumPy/SciPy/PETSc "
                "internal temporaries or workspace"
            ),
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
                streamed=self.port_coupling_mode == "streamed",
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
            if self.port_coupling_mode == "cached":
                xib = np.ascontiguousarray(lu_solve(factor, bi))
                bhat = np.ascontiguousarray(bt + trace_from_interior @ bi)
                dhat = np.ascontiguousarray(dt + di @ recovery)
            else:
                xib = bhat = dhat = None
            # ``recovery=-Vii^{-1}Vit``; hence ``Dt-Di*Xit=Dt+Di*recovery``.
            for row in range(nt):
                original = int(cell.trace_original_dofs[row])
                if original not in constraints.original_to_active:
                    if np.any(bt[row]) or np.any(dt[:, row]):
                        raise ValueError("local port coupling touches an MPC slave trace row")
            for values in (schur, recovery, trace_from_interior, bi, bt, di, dt, h):
                if values is not None and not np.isfinite(values).all():
                    raise ValueError("local p6 carrier data contains non-finite values")
            for values in (bhat, dhat, xib):
                if values is not None and not np.isfinite(values).all():
                    raise ValueError("local p6 condensed port data contains non-finite values")
            port_indices = np.asarray(ports, dtype=PETSc.IntType).copy()
            port_indices.flags.writeable = False
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
                    ports=port_indices,
                    Bhat=None if bhat is None else _readonly(bhat),
                    Dhat=None if dhat is None else _readonly(dhat),
                    XiB=None if xib is None else _readonly(xib),
                    Hlocal=None if h is None else _readonly(h),
                )
            )
        return tuple(result)

    def _prepare_direct_terms(self) -> None:
        constraints = self.condensed.trace_constraints
        if self._direct_terms_are_owned:
            seen_ports: set[int] = set()
            for term in self._direct_terms:
                port = int(term.port_index)
                if port < 0 or port >= self.condensed.appended_rows:
                    raise ValueError("direct trace port index is outside H_p")
                if port in seen_ports:
                    raise ValueError("owned direct trace terms must have one entry per port")
                seen_ports.add(port)
                for side, rows, values, original_map, active_map in (
                    (
                        "B",
                        term.B_original_rows,
                        term.B_values,
                        self._direct_B_original,
                        self._direct_B_active,
                    ),
                    (
                        "D",
                        term.D_original_rows,
                        term.D_values,
                        self._direct_D_original,
                        self._direct_D_active,
                    ),
                ):
                    rows = np.asarray(rows)
                    values = np.asarray(values)
                    if (
                        rows.ndim != 1
                        or values.ndim != 1
                        or rows.dtype != np.dtype(PETSc.IntType)
                        or values.dtype != np.dtype(np.complex128)
                        or not rows.flags.c_contiguous
                        or not values.flags.c_contiguous
                        or rows.size != values.size
                    ):
                        raise ValueError(
                            f"owned direct {side} carrier arrays are not normalized"
                        )
                    for start in range(
                        0, values.size, P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES
                    ):
                        stop = min(
                            start + P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES,
                            values.size,
                        )
                        if not np.isfinite(values[start:stop]).all():
                            raise ValueError(
                                f"owned direct {side} carrier contains non-finite values"
                            )
                    if rows.size == 0:
                        continue
                    active_rows = np.empty(rows.size, dtype=PETSc.IntType)
                    active_values = np.empty(rows.size, dtype=np.complex128)
                    for index, original in enumerate(rows):
                        try:
                            active_rows[index] = constraints.original_to_active[int(original)]
                        except KeyError as exc:
                            raise ValueError(
                                f"direct {side} carrier contains an MPC slave or unknown trace row"
                            ) from exc
                    np.copyto(active_values, values)
                    original_map[port] = (rows, values)
                    active_map[port] = (active_rows, active_values)
            return

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
        """Return the dense legacy H_p copy when that representation exists."""

        if self._H_p is None:
            raise RuntimeError("H_p is stored by the explicit port-block representation")
        return self._H_p.copy()

    def _apply_original_h(self, values: Any) -> np.ndarray:
        if self._H_p is not None:
            return np.ascontiguousarray(self._H_p @ values)
        assert self._original_port_block is not None
        return self._original_port_block.apply(values)

    def _original_h_solve(self, values: Any) -> np.ndarray:
        if self._H_p is not None:
            return np.ascontiguousarray(np.linalg.solve(self._H_p, values))
        assert self._original_port_block is not None
        return self._original_port_block.solve(values)

    @property
    def port_block_representation_identity(self) -> Mapping[str, Any] | None:
        if self.port_block_layout != RESEARCH_PORT_LAYOUT:
            return None
        assert self._original_port_block is not None and self._condensed_port_block is not None
        return MappingProxyType(port_block_representation_identity(
            self._original_port_block, self._condensed_port_block, layout=self.port_block_layout
        ))

    def _materialize_Hhat(self) -> np.ndarray:
        if self.port_block_layout == RESEARCH_PORT_LAYOUT:
            if self._Hhat is not None:
                return self._Hhat.copy()
            assert self._original_port_block is not None and self._condensed_port_block is not None
            if isinstance(self._original_port_block, DiagonalOriginalPortBlock):
                result = self._original_port_block.materialize_for_small_oracle(
                    max_bytes=16 * self.condensed.appended_rows**2
                )
            else:
                result = np.array(self._original_port_block._matrix, copy=True, order="C")
            for correction in self._condensed_port_block._corrections:
                result[np.ix_(correction.port_indices, correction.port_indices)] += (
                    correction.Di @ correction.XiB
                )
            return result
        if self._Hhat is not None:
            return self._Hhat.copy()
        # Explicit requests may build this block temporarily.  The streamed
        # apply path never calls this method and retains only the original H_p.
        assert self._H_p is not None
        result = self._H_p.copy()
        for cell in self._cells:
            if not len(cell.ports):
                continue
            xi_b = lu_solve(cell.interior_lu, cell.Bi)
            self._streamed_hhat_lu_solve_count += 1
            result[np.ix_(cell.ports, cell.ports)] += cell.Di @ xi_b
            del xi_b
        return result

    @property
    def Hhat(self) -> np.ndarray:
        """Return a copy, materializing Hhat on demand in streamed mode."""

        return self._materialize_Hhat()

    @property
    def audit(self) -> Mapping[str, Any]:
        self._audit["apply_count"] = int(self._apply_count)
        self._audit["hp_solve_count"] = int(self._hp_solve_count)
        self._audit["streamed_action_lu_solve_count"] = int(
            self._streamed_action_lu_solve_count
        )
        self._audit["streamed_recovery_lu_solve_count"] = int(
            self._streamed_recovery_lu_solve_count
        )
        self._audit["streamed_hhat_lu_solve_count"] = int(
            self._streamed_hhat_lu_solve_count
        )
        self._audit["streamed_max_local_scratch_bytes"] = int(
            self._streamed_max_local_scratch_bytes
        )
        return MappingProxyType(self._audit)

    @property
    def buffer_inventory(self) -> Mapping[str, Any]:
        """Count resident carrier arrays by backing owner, not view identity."""

        raw_fields = ("Bi", "Bt", "Di", "Dt", "Hlocal")
        transformed_fields = ("Bhat", "Dhat", "XiB")
        payload_arrays = []
        for cell in self._cells:
            payload_arrays.extend(
                value for value in (getattr(cell, name) for name in raw_fields)
                if value is not None
            )
            payload_arrays.extend(
                value for value in (getattr(cell, name) for name in transformed_fields)
                if value is not None
            )
            payload_arrays.append(cell.ports)

        staging_arrays = []
        if self.port_coupling_mode == "cached":
            for term in self._port_terms.values():
                staging_arrays.extend(
                    value
                    for value in (term.Bi, term.Di, term.Bt, term.Dt, term.H)
                    if value is not None
                )
        direct_arrays = [
            value
            for mapping in (
                self._direct_B_original,
                self._direct_D_original,
                self._direct_B_active,
                self._direct_D_active,
            )
            for pair in mapping.values()
            for value in pair
        ]
        owners: dict[int, int] = {}
        for value in (*payload_arrays, *staging_arrays, *direct_arrays):
            owner = value
            while isinstance(getattr(owner, "base", None), np.ndarray):
                owner = owner.base
            owners[id(owner)] = int(owner.nbytes)

        def bytes_for(fields: tuple[str, ...]) -> int:
            return int(sum(
                getattr(cell, name).nbytes
                for cell in self._cells
                for name in fields
                if getattr(cell, name) is not None
            ))

        def direct_bytes(mapping: Mapping[int, tuple[np.ndarray, np.ndarray]]) -> int:
            return int(sum(array.nbytes for pair in mapping.values() for array in pair))

        staging_bytes = int(sum(array.nbytes for array in staging_arrays))
        direct_payload_bytes = sum(
            direct_bytes(mapping)
            for mapping in (
                self._direct_B_original,
                self._direct_D_original,
                self._direct_B_active,
                self._direct_D_active,
            )
        )
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
                "port_coupling_mode": self.port_coupling_mode,
                "raw_port_payload_bytes_sum": bytes_for(raw_fields),
                "transformed_port_payload_bytes_sum": bytes_for(transformed_fields),
                "staging_port_payload_bytes_sum": staging_bytes,
                "direct_trace_payload_bytes_sum": int(direct_payload_bytes),
                "local_carrier_cell_payload_bytes": int(
                    bytes_for(raw_fields) + bytes_for(transformed_fields)
                ),
                "all_port_payload_bytes_sum_with_aliases": int(
                    bytes_for(raw_fields)
                    + bytes_for(transformed_fields)
                    + staging_bytes
                    + direct_payload_bytes
                ),
                "unique_port_payload_owner_count": len(owners),
                "unique_port_payload_owner_bytes": int(sum(owners.values())),
                "resident_H_p_bytes": int(
                    self._H_p.nbytes if self._H_p is not None else
                    sum(array.nbytes for array in self._original_port_block.numeric_arrays)
                ),
                "original_H_representation": self.port_block_layout,
                "resident_Hhat_bytes": 0 if self._Hhat is None else int(self._Hhat.nbytes),
                "Hhat_materialized": self._Hhat is not None,
                "per_cell_transformed_arrays_resident": self.port_coupling_mode == "cached",
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
                "H_p_sha256": (
                    _array_sha256(self._H_p) if self._H_p is not None
                    else self._original_port_block.identity_sha256
                ),
                "port_block_representation_identity": (
                    None if self.port_block_layout == LEGACY_PORT_LAYOUT
                    else dict(self.port_block_representation_identity)
                ),
                "Hhat_sha256": None if self._Hhat is None else _array_sha256(self._Hhat),
                "Hhat_materialized": self._Hhat is not None,
                "port_coupling_mode": self.port_coupling_mode,
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
                "port_coupling_mode": self.port_coupling_mode,
                "trace_action": (
                    "MPI1 owner-local S_V/Bhat/Dhat cached multiply"
                    if self.port_coupling_mode == "cached"
                    else "MPI1 bounded owner-local Bi/Di actions with cached S_V and conjugate-transpose scatter"
                ),
                "port_action": (
                    "cached Hhat plus sparse direct trace terms"
                    if self.port_coupling_mode == "cached"
                    else "original Hp plus per-cell streamed Di*solve(Bi*alpha), no resident Hhat"
                ),
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

    @staticmethod
    def _streamed_cell_action(cell: Any, local_trace: np.ndarray, alpha: np.ndarray):
        """Apply one cell's local trace/port terms and report named scratch."""

        local_action = np.asarray(cell.S_V @ local_trace, dtype=np.complex128).reshape(-1)
        port_action = None
        local_lu_solve_calls = 0
        scratch_bytes = int(local_trace.nbytes + local_action.nbytes)
        if len(cell.ports):
            local_alpha = alpha[cell.ports]
            bi_alpha = cell.Bi @ local_alpha
            b_action = cell.Bt @ local_alpha
            trace_from_b = cell.trace_from_interior @ bi_alpha
            b_action += trace_from_b
            local_action += b_action

            recovery_trace = cell.recovery @ local_trace
            di_recovery_trace = cell.Di @ recovery_trace
            dt_trace = cell.Dt @ local_trace
            xi_b_alpha = lu_solve(cell.interior_lu, bi_alpha)
            local_lu_solve_calls += 1
            di_xi_b_alpha = cell.Di @ xi_b_alpha
            port_action = -dt_trace.copy()
            port_action -= di_recovery_trace
            port_action += di_xi_b_alpha
            scratch_bytes = sum(
                array.nbytes
                for array in (
                    local_trace,
                    local_action,
                    local_alpha,
                    bi_alpha,
                    b_action,
                    trace_from_b,
                    recovery_trace,
                    di_recovery_trace,
                    dt_trace,
                    xi_b_alpha,
                    di_xi_b_alpha,
                    port_action,
                )
            )
            del (
                local_alpha,
                bi_alpha,
                b_action,
                trace_from_b,
                recovery_trace,
                di_recovery_trace,
                dt_trace,
                xi_b_alpha,
                di_xi_b_alpha,
            )
        return local_action, port_action, int(scratch_bytes), local_lu_solve_calls

    def _apply_streamed_array(self, source: np.ndarray) -> np.ndarray:
        active = source[: self.condensed.active_rows]
        alpha = source[self.condensed.active_rows :]
        result = np.zeros_like(source)
        port_offset = self.condensed.active_rows
        local_lu_solve_calls = 0
        for cell in self._cells:
            local_trace = np.asarray(
                cell.expansion @ active[cell.active_ids], dtype=np.complex128
            ).reshape(-1)
            local_action, port_action, scratch_bytes, cell_solve_calls = (
                self._streamed_cell_action(cell, local_trace, alpha)
            )
            self._streamed_max_local_scratch_bytes = max(
                self._streamed_max_local_scratch_bytes, scratch_bytes
            )
            local_lu_solve_calls += cell_solve_calls
            if port_action is not None:
                result[port_offset + cell.ports] += port_action
            result[cell.active_ids] += np.asarray(
                cell.expansion.conjugate().T @ local_action
            ).reshape(-1)
            del local_trace, local_action, port_action

        hp_action = self._apply_original_h(alpha)
        self._streamed_max_local_scratch_bytes = max(
            self._streamed_max_local_scratch_bytes, int(hp_action.nbytes)
        )
        result[port_offset:] += hp_action
        del hp_action
        self._add_direct_reduced(result, alpha, active)
        self._streamed_action_lu_solve_count += local_lu_solve_calls
        self._apply_count += 1
        return np.ascontiguousarray(result)

    def _apply_array(self, value: Any) -> np.ndarray:
        source = self._check_reduced_array(value, "reduced source")
        if self.port_coupling_mode == "streamed":
            return self._apply_streamed_array(source)
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
        if self._Hhat is not None:
            result[self.condensed.active_rows :] += self._Hhat @ alpha
        else:
            result[self.condensed.active_rows :] += self._condensed_port_block.apply(alpha)
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

    def iter_reduced_contribution_layouts(
        self, *, hhat_block_columns: int | None = None
    ):
        """Yield row/column metadata without computing any local Schur values.

        This metadata-only walk lets the Task40 V13 q assembler build a sparse
        superset pattern before its single numerical contribution pass.
        """
        if self._destroyed or getattr(self.condensed, "_destroyed", False):
            raise RuntimeError("p6 contribution owner has been destroyed")
        if self.condensed.comm.Get_size() != 1 or self.port_coupling_mode != "cached":
            raise ValueError("reduced contribution layouts require MPI1 cached port terms")
        trace_rows = int(self.condensed.active_rows)
        total_rows = self.reduced_size
        port_count = int(self.condensed.appended_rows)
        if total_rows <= 0 or total_rows > int(np.iinfo(PETSc.IntType).max):
            raise OverflowError("reduced matrix row range exceeds PETSc.IntType")

        ports = np.arange(trace_rows, total_rows, dtype=PETSc.IntType)
        port_count = len(ports)
        if hhat_block_columns is None:
            yield ports, ports, "ports/Hhat"
        else:
            if type(hhat_block_columns) is not int or hhat_block_columns <= 0:
                raise ValueError("Hhat block-column width must be a positive integer")
            for start in range(0, port_count, hhat_block_columns):
                stop = min(start + hhat_block_columns, port_count)
                yield ports, ports[start:stop], f"ports/Hhat/{start}:{stop}"
        del ports
        for cell_index, cell in enumerate(self._cells):
            yield cell.active_ids, cell.active_ids, f"volume/cell/{cell_index}"
            if not len(cell.ports):
                continue
            if cell.Bhat is None or cell.Dhat is None:
                raise ValueError("cached p6 trace/port formulas are unavailable")
            port_indices = np.asarray(cell.ports, dtype=PETSc.IntType)
            global_ports = trace_rows + port_indices
            yield cell.active_ids, global_ports, f"cell/C_hat/{cell_index}"
            yield global_ports, cell.active_ids, f"cell/-D_hat/{cell_index}"
            del port_indices, global_ports

        for port, (rows, _values) in sorted(self._direct_B_active.items()):
            port_id = np.asarray([trace_rows + port], dtype=PETSc.IntType)
            yield rows, port_id, f"direct/C/port/{port}"
            del port_id
        for port, (columns, values) in sorted(self._direct_D_active.items()):
            port_id = np.asarray([trace_rows + port], dtype=PETSc.IntType)
            yield port_id, columns, f"direct/-D/port/{port}"
            del port_id

    def iter_reduced_contributions(
        self,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
        hhat_block_columns: int | None = None,
    ):
        """Yield the complete cached reduced matrix as one bounded block at a time.

        This is the assembly seam for exact quotient solvers. It emits the
        same Schur, trace/port, and direct-carrier terms as ``_apply_array``;
        consumers must finish their projection and release each yielded block
        before requesting the next one. No full reduced matrix is constructed.
        """
        from .static_local_schur_action import iter_owned_constrained_schur_contributions

        if not callable(allocation_gate):
            raise ValueError("fresh whole-tree contribution allocation gate required")
        if self._destroyed or getattr(self.condensed, "_destroyed", False):
            raise RuntimeError("p6 contribution owner has been destroyed")
        if self.condensed.comm.Get_size() != 1 or self.port_coupling_mode != "cached":
            raise ValueError("reduced contributions require MPI1 cached port terms")
        trace_rows = int(self.condensed.active_rows)
        total_rows = self.reduced_size
        port_count = int(self.condensed.appended_rows)
        index_bytes = np.dtype(PETSc.IntType).itemsize
        if total_rows <= 0 or total_rows > int(np.iinfo(PETSc.IntType).max):
            raise OverflowError("reduced matrix row range exceeds PETSc.IntType")

        def gate(label: str, payload: int = 0, workspace: int = 0) -> None:
            if self._destroyed or getattr(self.condensed, "_destroyed", False):
                raise RuntimeError("contribution owner destroyed during iteration")
            allocation_gate("p6_reduced_contribution/" + label, {
                "matrix_payload_bytes": int(payload),
                "workspace_bytes": int(workspace),
                "allocation_semantics": "additional_objects_to_current_resident_RSS",
                "consumer_must_release_before_next": True,
                "global_q_factor_count": 0,
                "PETSc_index_itemsize_bytes": index_bytes,
            })

        def checked(rows: Any, columns: Any, block: Any, label: str):
            rows = np.asarray(rows)
            columns = np.asarray(columns)
            block = np.asarray(block)
            for indices in (rows, columns):
                if (indices.ndim != 1 or indices.dtype.kind not in "iu"
                        or (indices.size and (int(indices.min()) < 0 or int(indices.max()) >= total_rows))
                        or len(np.unique(indices)) != len(indices)):
                    raise ValueError("invalid p6 reduced contribution indices")
            if (block.shape != (len(rows), len(columns))
                    or block.dtype != np.dtype(np.complex128)
                    or not np.isfinite(block).all()):
                raise ValueError("invalid finite complex128 p6 reduced contribution block")
            row_view, column_view, block_view = rows.view(), columns.view(), block.view()
            row_view.setflags(write=False)
            column_view.setflags(write=False)
            block_view.setflags(write=False)
            return row_view, column_view, block_view, label

        ports = np.arange(trace_rows, total_rows, dtype=PETSc.IntType)
        if hhat_block_columns is None:
            hhat_bytes = int(16 * port_count * port_count)
            gate("ports/Hhat", hhat_bytes, hhat_bytes)
            hhat = self._materialize_Hhat()
            yield checked(ports, ports, hhat, "ports/Hhat")
            del hhat
        else:
            if type(hhat_block_columns) is not int or hhat_block_columns <= 0:
                raise ValueError("Hhat block-column width must be a positive integer")
            for start in range(0, port_count, hhat_block_columns):
                stop = min(start + hhat_block_columns, port_count)
                width = stop - start
                label = f"ports/Hhat/{start}:{stop}"
                block_bytes = int(16 * port_count * width)
                max_internal_width = max(
                    (int(cell.Bi.shape[0]) for cell in self._cells), default=0
                )
                max_cell_port_width = max(
                    (len(cell.ports) for cell in self._cells), default=0
                )
                if self.port_block_layout == RESEARCH_PORT_LAYOUT:
                    assert self._condensed_port_block is not None
                    max_internal_width = max(
                        (
                            int(correction.XiB.shape[0])
                            for correction in self._condensed_port_block._corrections
                        ),
                        default=max_internal_width,
                    )
                    max_cell_port_width = max(
                        (
                            len(correction.port_indices)
                            for correction in self._condensed_port_block._corrections
                        ),
                        default=max_cell_port_width,
                    )
                local_width = min(width, max_cell_port_width)
                xi_b_copy = int(16 * max_internal_width * local_width)
                uncached_bi_copy = 0
                if self.port_block_layout != RESEARCH_PORT_LAYOUT:
                    max_uncached_internal_width = max(
                        (int(cell.Bi.shape[0]) for cell in self._cells if cell.XiB is None),
                        default=0,
                    )
                    uncached_bi_copy = int(16 * max_uncached_internal_width * local_width)
                local_delta = int(16 * max_cell_port_width * local_width)
                indexed_target_copy = local_delta
                # Count Di@XiB output and any dtype conversion copy, selected and
                # output-column arrays, correction port indices, and Boolean masks.
                index_workspace = int(16 * max_cell_port_width + 32 * width)
                basis_workspace = block_bytes
                hhat_workspace = (
                    basis_workspace
                    + xi_b_copy
                    + uncached_bi_copy
                    + 2 * local_delta
                    + indexed_target_copy
                    + index_workspace
                )
                gate(
                    label,
                    block_bytes,
                    hhat_workspace,
                )
                basis = np.zeros((port_count, width), dtype=np.complex128)
                basis[np.arange(start, stop), np.arange(width)] = 1.0
                hhat_block = np.asarray(
                    self._apply_original_h(basis), dtype=np.complex128
                )
                del basis

                if self.port_block_layout == RESEARCH_PORT_LAYOUT:
                    assert self._condensed_port_block is not None
                    for correction in self._condensed_port_block._corrections:
                        correction_ports = np.asarray(
                            correction.port_indices, dtype=np.int64
                        )
                        selected = np.flatnonzero(
                            (correction_ports >= start) & (correction_ports < stop)
                        )
                        if not len(selected):
                            continue
                        output_columns = correction_ports[selected] - start
                        xi_b = correction.XiB[:, selected]
                        delta = np.asarray(correction.Di @ xi_b, dtype=np.complex128)
                        hhat_block[np.ix_(correction_ports, output_columns)] += delta
                        del xi_b, delta, selected, output_columns
                else:
                    for cell in self._cells:
                        cell_ports = np.asarray(cell.ports, dtype=np.int64)
                        selected = np.flatnonzero(
                            (cell_ports >= start) & (cell_ports < stop)
                        )
                        if not len(selected):
                            continue
                        output_columns = cell_ports[selected] - start
                        xi_b = (
                            cell.XiB[:, selected]
                            if cell.XiB is not None
                            else lu_solve(cell.interior_lu, cell.Bi[:, selected])
                        )
                        if cell.XiB is None:
                            self._streamed_hhat_lu_solve_count += 1
                        delta = np.asarray(cell.Di @ xi_b, dtype=np.complex128)
                        hhat_block[np.ix_(cell_ports, output_columns)] += delta
                        del xi_b, delta, selected, output_columns

                yield checked(ports, ports[start:stop], hhat_block, label)
                del hhat_block
        del ports

        for cell_index, cell in enumerate(self._cells):
            active_count = len(cell.active_ids)
            local_trace_count = len(cell.original_trace)
            expansion_bytes = sum(array.nbytes for array in (
                cell.expansion.data, cell.expansion.indices, cell.expansion.indptr
            ))
            gate(
                f"volume/cell/{cell_index}",
                16 * active_count * active_count + active_count * index_bytes,
                2 * expansion_bytes + cell.expansion.nnz * 224
                + 16 * (active_count * local_trace_count + 2 * active_count * active_count)
                + active_count * active_count,
            )
            _index, active_ids, schur = next(
                iter_owned_constrained_schur_contributions(self.condensed, (cell_index,))
            )
            if not np.array_equal(active_ids, cell.active_ids):
                raise ValueError("inherited p6 Schur and carrier active-row order differs")
            yield checked(active_ids, active_ids, schur, f"volume/cell/{cell_index}")
            del active_ids, schur

            port_indices = np.asarray(cell.ports, dtype=PETSc.IntType)
            if not len(port_indices):
                continue
            if cell.Bhat is None or cell.Dhat is None:
                raise ValueError("cached p6 trace/port formulas are unavailable")
            global_ports = trace_rows + port_indices
            gate(f"cell/C_hat/{cell_index}", index_bytes * len(global_ports)
                 + 16 * active_count * len(global_ports),
                 expansion_bytes + active_count * len(global_ports) * 16)
            c_hat = np.asarray(cell.expansion.conjugate().T @ cell.Bhat, dtype=np.complex128)
            yield checked(cell.active_ids, global_ports, c_hat, f"cell/C_hat/{cell_index}")
            del c_hat
            gate(f"cell/-D_hat/{cell_index}", 16 * len(global_ports) * active_count,
                 expansion_bytes + 16 * len(global_ports) * active_count)
            d_hat = -np.asarray(cell.expansion.T @ cell.Dhat.T, dtype=np.complex128).T
            yield checked(global_ports, cell.active_ids, d_hat, f"cell/-D_hat/{cell_index}")
            del d_hat, global_ports

        for port, (rows, values) in sorted(self._direct_B_active.items()):
            label = f"direct/C/port/{port}"
            gate(label, index_bytes, len(rows) * 16)
            port_id = np.asarray([trace_rows + port], dtype=PETSc.IntType)
            block = np.asarray(values, dtype=np.complex128).reshape(-1, 1)
            yield checked(rows, port_id, block, label)
            del port_id, block
        for port, (columns, values) in sorted(self._direct_D_active.items()):
            label = f"direct/-D/port/{port}"
            gate(label, index_bytes + values.nbytes, len(columns) * 16)
            port_id = np.asarray([trace_rows + port], dtype=PETSc.IntType)
            block = -np.asarray(values, dtype=np.complex128).reshape(1, -1)
            yield checked(port_id, columns, block, label)
            del port_id, block

    def original_hp_solve(self, rhs: Any) -> np.ndarray:
        """Solve with the original ``H_p`` (never with ``Hhat``)."""

        values = _complex_vector(rhs, "H_p RHS", size=self.condensed.appended_rows)
        result = self._original_h_solve(values)
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
            solved_rhs = lu_solve(cell.interior_lu, bi)
            trace_recovery = cell.recovery @ local_trace
            values = solved_rhs + trace_recovery
            if self.port_coupling_mode == "streamed":
                self._streamed_max_local_scratch_bytes = max(
                    self._streamed_max_local_scratch_bytes,
                    int(sum(array.nbytes for array in (
                        local_trace, bi, solved_rhs, trace_recovery, values
                    ))),
                )
            del local_trace, bi, solved_rhs, trace_recovery
            if len(cell.ports):
                if self.port_coupling_mode == "streamed":
                    local_alpha = alpha[cell.ports]
                    bi_alpha = cell.Bi @ local_alpha
                    xi_b_alpha = lu_solve(cell.interior_lu, bi_alpha)
                    self._streamed_recovery_lu_solve_count += 1
                    self._streamed_max_local_scratch_bytes = max(
                        self._streamed_max_local_scratch_bytes,
                        int(sum(array.nbytes for array in (
                            local_alpha, bi_alpha, xi_b_alpha, values
                        ))),
                    )
                    values -= xi_b_alpha
                    del local_alpha, bi_alpha, xi_b_alpha
                else:
                    assert cell.XiB is not None
                    values = values - cell.XiB @ alpha[cell.ports]
            result[cell.original_interiors] = values
            if self.port_coupling_mode == "streamed":
                del values
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
        augmented_port_residual = ports_rhs + port_action - self._apply_original_h(alpha)
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
            + float(np.linalg.norm(self._apply_original_h(alpha)))
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
            "port_hp_solution_norm": float(np.linalg.norm(self._apply_original_h(alpha))),
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
    port_coupling_mode: str = "cached",
    bounded_direct_term_build: bool = False,
    port_block_layout: str = LEGACY_PORT_LAYOUT,
    original_port_block: Any | None = None,
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
    if port_block_layout == LEGACY_PORT_LAYOUT:
        if original_port_block is not None:
            raise ValueError("legacy layout does not accept original_port_block")
        if H_p is None:
            hp = np.zeros((condensed.appended_rows, condensed.appended_rows), dtype=np.complex128)
            for port, entry in enumerate(entries):
                hp[port, port] = complex(getattr(entry, "normalization_h"))
        else:
            hp = _complex_matrix(H_p, "H_p", shape=(condensed.appended_rows, condensed.appended_rows))
    elif port_block_layout == RESEARCH_PORT_LAYOUT:
        if H_p is not None or not isinstance(
            original_port_block, (DiagonalOriginalPortBlock, DenseOriginalPortBlock)
        ):
            raise ValueError("research layout requires H_p=None and an explicit original_port_block")
        if original_port_block.count != condensed.appended_rows:
            raise ValueError("original_port_block size differs from the carrier mode count")
        hp = None
    else:
        raise ValueError("unknown original/condensed port-block layout")
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

    direct_row_chunk = (
        np.empty(P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES, dtype=np.int64)
        if bounded_direct_term_build
        else None
    )
    direct_value_chunk = (
        np.empty(P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES, dtype=np.complex128)
        if bounded_direct_term_build
        else None
    )

    def consume(rows: Any, values: Any, port: int, target: dict[int, dict[int, dict[int, complex]]] | None, side: str) -> tuple[np.ndarray, np.ndarray]:
        if bounded_direct_term_build:
            if not isinstance(rows, np.ndarray) or not isinstance(values, np.ndarray):
                raise TypeError("bounded carrier construction requires NumPy row/value arrays")
            if not rows.flags.c_contiguous or not values.flags.c_contiguous:
                raise ValueError("bounded carrier construction requires contiguous row/value arrays")
            row_source = rows.reshape(-1)
            value_source = values.reshape(-1)
            if row_source.dtype.kind not in "iu" or value_source.dtype.kind not in "biufc":
                raise ValueError("bounded carrier row/value arrays must be numeric")
            if row_source.size != value_source.size:
                raise ValueError(f"carrier {side} row/value shape mismatch")
            if direct_row_chunk is None or direct_value_chunk is None:
                raise RuntimeError("bounded carrier scratch buffers are missing")
            output_rows = np.empty(row_source.size, dtype=PETSc.IntType)
            output_values = np.empty(value_source.size, dtype=np.complex128)
            output_size = 0
            for start in range(0, row_source.size, P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES):
                stop = min(start + P6_DIRECT_TERM_BUILD_CHUNK_ENTRIES, row_source.size)
                count = stop - start
                rows_chunk = direct_row_chunk[:count]
                values_chunk = direct_value_chunk[:count]
                np.copyto(rows_chunk, row_source[start:stop], casting="unsafe")
                np.copyto(values_chunk, value_source[start:stop], casting="unsafe")
                if not np.isfinite(values_chunk).all():
                    raise ValueError(f"carrier {side} values contain non-finite values")
                for row_value, value in zip(rows_chunk, values_chunk, strict=True):
                    row = int(row_value)
                    value = complex(value)
                    location = interior_locations.get(row)
                    if location is not None:
                        if target is None:
                            raise RuntimeError("internal carrier target is missing")
                        cell_index, local = location
                        target[cell_index][port][local] = (
                            target[cell_index][port].get(local, 0.0) + value
                        )
                    else:
                        if row not in constraints.original_to_active:
                            raise ValueError(
                                "carrier includes an MPC slave or unknown trace row"
                            )
                        output_rows[output_size] = row
                        output_values[output_size] = value
                        output_size += 1
            return output_rows[:output_size], output_values[:output_size]

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
        direct_terms_are_owned=bounded_direct_term_build,
        owns_condensed=owns_condensed,
        port_coupling_mode=port_coupling_mode,
        port_block_layout=port_block_layout,
        original_port_block=original_port_block,
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
    "P6MatrixFreeHhatTerm",
    "P6CellCondensedAction",
    "P6CellPortTerms",
    "P6DirectTracePortTerms",
    "P6RetainedBALHBridge",
    "apply_p6_hhat_vector_action",
    "build_p6_cell_condensed_action_from_carrier",
    "condense_physical_cell_blocks",
    "native_residual_from_augmented",
    "raw_plane_D_action_from_global_normalized",
)
