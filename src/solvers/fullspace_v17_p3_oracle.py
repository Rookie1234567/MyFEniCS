"""Oracle-only exact p3 physical coarse-span operations.

The functions here are intentionally adapters around already-built physical
objects.  They never become a production PC and never build the p6 physical
matrix.  A caller supplies the assembled diagnostic p3 matrix and the exact
matrix-free p6 action; the returned facts expose the three-stage lifecycle and
the raw norms needed by the V17 checker.
"""

from __future__ import annotations

from collections.abc import Mapping
import ctypes
import ctypes.util
import hashlib
from typing import Any

import numpy as np


ORACLE_A_SCHEMA = "task038.v17.exact-p3-coarse-span.v1"
ORACLE_A_RESIDUAL_LIMIT = 1.0e-10
ORACLE_A_RHO3_LIMIT = 1.0e-6
ORACLE_A_RHO_REF_LIMIT = 0.70
ORACLE_A_PARENT_WARNING_BYTES = 10_000_000_000
ORACLE_A_PARENT_HARD_BYTES = 12_000_000_000


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if callable(destroy):
        destroy()


def _array(value: Any) -> np.ndarray:
    if hasattr(value, "array"):
        return np.asarray(value.array)
    getter = getattr(value, "getArray", None)
    if callable(getter):
        try:
            return np.asarray(getter(readonly=True))
        except TypeError:
            return np.asarray(getter())
    return np.asarray(value)


def _vector_facts(value: Any) -> dict[str, Any]:
    values = np.asarray(_array(value), dtype=np.complex128)
    finite = bool(np.all(np.isfinite(values)))
    norm = float(value.norm()) if callable(getattr(value, "norm", None)) else float(np.linalg.norm(values))
    return {
        "norm": norm,
        "finite": finite and np.isfinite(norm),
        "local_size": int(values.size),
        "array_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(values)).cast("B")
        ).hexdigest(),
    }


def _new_vector(matrix: Any, side: str) -> Any:
    factory = getattr(matrix, f"createVec{side}", None)
    if not callable(factory):
        raise TypeError(f"matrix has no createVec{side} factory")
    return factory()


def _relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        denominator = max(float(right.norm()), np.finfo(float).tiny)
        return float(difference.norm()) / denominator
    finally:
        _destroy(difference)


class _MatFactorInfo(ctypes.Structure):
    """PETSc 3.19 ``MatFactorInfo`` in header order (eleven PetscReal)."""

    _fields_ = [
        ("diagonal_fill", ctypes.c_double),
        ("usedt", ctypes.c_double),
        ("dt", ctypes.c_double),
        ("dtcol", ctypes.c_double),
        ("dtcount", ctypes.c_double),
        ("fill", ctypes.c_double),
        ("levels", ctypes.c_double),
        ("pivotinblocks", ctypes.c_double),
        ("zeropivot", ctypes.c_double),
        ("shifttype", ctypes.c_double),
        ("shiftamount", ctypes.c_double),
    ]


def _petsc_handle(value: Any) -> ctypes.c_void_p:
    handle = getattr(value, "handle", value)
    if isinstance(handle, ctypes.c_void_p):
        return handle
    return ctypes.c_void_p(int(handle))


def _petsc_error(code: int, operation: str) -> None:
    if int(code) != 0:
        raise RuntimeError(f"{operation} returned PETSc error code {int(code)}")


def _load_petsc_api() -> ctypes.CDLL:
    names = []
    found = ctypes.util.find_library("petsc_complex")
    if found:
        names.append(found)
    names.extend(("libpetsc_complex.so.3.19", "libpetsc_complex.so"))
    for name in names:
        try:
            library = ctypes.CDLL(name)
        except OSError:
            continue
        void = ctypes.c_void_p
        library.MatGetFactor.argtypes = [void, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(void)]
        library.MatGetFactor.restype = ctypes.c_int
        library.MatFactorInfoInitialize.argtypes = [ctypes.POINTER(_MatFactorInfo)]
        library.MatFactorInfoInitialize.restype = ctypes.c_int
        library.MatFactorGetPreferredOrdering.argtypes = [void, ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        library.MatFactorGetPreferredOrdering.restype = ctypes.c_int
        library.MatLUFactorSymbolic.argtypes = [void, void, void, void, ctypes.POINTER(_MatFactorInfo)]
        library.MatLUFactorSymbolic.restype = ctypes.c_int
        library.MatLUFactorNumeric.argtypes = [void, void, ctypes.POINTER(_MatFactorInfo)]
        library.MatLUFactorNumeric.restype = ctypes.c_int
        library.MatSolve.argtypes = [void, void, void]
        library.MatSolve.restype = ctypes.c_int
        library.MatDestroy.argtypes = [ctypes.POINTER(void)]
        library.MatDestroy.restype = ctypes.c_int
        library.ISDestroy.argtypes = [ctypes.POINTER(void)]
        library.ISDestroy.restype = ctypes.c_int
        library.MatMumpsGetInfog.argtypes = [void, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        library.MatMumpsGetInfog.restype = ctypes.c_int
        library.MatMumpsGetRinfog.argtypes = [void, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        library.MatMumpsGetRinfog.restype = ctypes.c_int
        return library
    raise RuntimeError("qualified PETSc complex library was not found")


class _MumpsFactor:
    """One owned PETSc MUMPS factor: symbolic, then optional numeric/solve."""

    def __init__(self, matrix: Any) -> None:
        self._api = _load_petsc_api()
        self._handle = ctypes.c_void_p()
        _petsc_error(
            self._api.MatGetFactor(
                _petsc_handle(matrix), b"mumps", 1, ctypes.byref(self._handle)
            ),
            "MatGetFactor",
        )
        self._info = _MatFactorInfo()
        self._row_is = None
        self._col_is = None
        self._preferred_ordering = None
        self.symbolic_calls = 0
        self.numeric_calls = 0
        self.solve_calls = 0
        self.destroyed = False
        try:
            _petsc_error(
                self._api.MatFactorInfoInitialize(ctypes.byref(self._info)),
                "MatFactorInfoInitialize",
            )
            preferred = ctypes.c_char_p()
            _petsc_error(
                self._api.MatFactorGetPreferredOrdering(
                    self._handle, 1, ctypes.byref(preferred)
                ),
                "MatFactorGetPreferredOrdering",
            )
            self._preferred_ordering = (
                preferred.value.decode("ascii") if preferred.value else ""
            )
            if self._preferred_ordering != "external":
                self._row_is, self._col_is = matrix.getOrdering(self._preferred_ordering)
        except Exception:
            self.destroy()
            raise

    @property
    def preferred_ordering(self) -> str:
        return str(self._preferred_ordering)

    def symbolic(self, matrix: Any) -> None:
        if self.destroyed or self.symbolic_calls:
            raise RuntimeError("MUMPS symbolic analysis must run exactly once")
        _petsc_error(
            self._api.MatLUFactorSymbolic(
                self._handle,
                _petsc_handle(matrix),
                _petsc_handle(self._row_is)
                if self._row_is is not None
                else ctypes.c_void_p(),
                _petsc_handle(self._col_is)
                if self._col_is is not None
                else ctypes.c_void_p(),
                ctypes.byref(self._info),
            ),
            "MatLUFactorSymbolic",
        )
        self.symbolic_calls = 1

    def numeric(self, matrix: Any) -> None:
        if self.destroyed or self.symbolic_calls != 1 or self.numeric_calls:
            raise RuntimeError("MUMPS numeric factorization has an invalid lifecycle")
        _petsc_error(
            self._api.MatLUFactorNumeric(
                self._handle, _petsc_handle(matrix), ctypes.byref(self._info)
            ),
            "MatLUFactorNumeric",
        )
        self.numeric_calls = 1

    def solve(self, rhs: Any, solution: Any) -> None:
        if self.destroyed or self.numeric_calls != 1 or self.solve_calls:
            raise RuntimeError("MUMPS solve has an invalid lifecycle")
        _petsc_error(
            self._api.MatSolve(
                self._handle, _petsc_handle(rhs), _petsc_handle(solution)
            ),
            "MatSolve",
        )
        self.solve_calls = 1

    def info(self) -> dict[str, Any]:
        infog: dict[str, int] = {}
        rinfog: dict[str, float] = {}
        for index in range(1, 21):
            value = ctypes.c_int()
            code = self._api.MatMumpsGetInfog(self._handle, index, ctypes.byref(value))
            if int(code) != 0:
                break
            infog[str(index)] = int(value.value)
        for index in range(1, 21):
            value = ctypes.c_double()
            code = self._api.MatMumpsGetRinfog(self._handle, index, ctypes.byref(value))
            if int(code) != 0:
                break
            rinfog[str(index)] = float(value.value)
        return {"infog": infog, "rinfog": rinfog}

    def destroy(self) -> None:
        if self.destroyed:
            return
        for name in ("_row_is", "_col_is"):
            value = getattr(self, name)
            if value is not None:
                _destroy(value)
                setattr(self, name, None)
        if self._handle:
            _petsc_error(
                self._api.MatDestroy(ctypes.byref(self._handle)), "MatDestroy"
            )
            self._handle = ctypes.c_void_p()
        self.destroyed = True


def analyze_mumps_p3(matrix: Any) -> tuple[Any, dict[str, Any]]:
    """Create a MUMPS factor and run its symbolic analysis only.

    The PETSc C API is deliberately used directly because qualified petsc4py
    does not expose the required symbolic calls.  No numeric factor or solve
    is called here.  The caller owns the returned factor and must destroy it.
    """
    factor = _MumpsFactor(matrix)
    try:
        factor.symbolic(matrix)
    except Exception:
        factor.destroy()
        raise
    return factor, {
        "schema": "task038.v17.mumps-analysis.v1",
        "backend": "mumps",
        "analysis_only": True,
        "numeric_factor_called": False,
        "solve_called": False,
        "symbolic_calls": factor.symbolic_calls,
        "numeric_calls": factor.numeric_calls,
        "solve_calls": factor.solve_calls,
        "preferred_ordering": factor.preferred_ordering,
        "ordering_via": (
            "mumps_internal_auto_icntl7"
            if factor.preferred_ordering == "external"
            else "PETSc_MatGetOrdering"
        ),
        "raw_info": factor.info(),
    }


def solve_mumps_p3(
    factor: Any,
    matrix: Any,
    rhs: Any,
    *,
    predicted_peak_bytes: int,
    hard_limit_bytes: int = ORACLE_A_PARENT_HARD_BYTES,
) -> tuple[Any | None, dict[str, Any]]:
    """Run numeric factorization and solve on the already analyzed factor."""

    predicted_peak_bytes = int(predicted_peak_bytes)
    hard_limit_bytes = int(hard_limit_bytes)
    if predicted_peak_bytes >= hard_limit_bytes:
        return None, {
            "schema": "task038.v17.mumps-solve.v1",
            "backend": "mumps",
            "resource_preflight": "blocked",
            "predicted_peak_bytes": predicted_peak_bytes,
            "hard_limit_bytes": hard_limit_bytes,
            "analysis_only": True,
            "numeric_factor_called": False,
            "solve_called": False,
        }
    if not isinstance(factor, _MumpsFactor):
        raise TypeError("solve_mumps_p3 requires the factor returned by analyze_mumps_p3")
    solution = None
    try:
        factor.numeric(matrix)
        solution = _new_vector(matrix, "Right")
        factor.solve(rhs, solution)
        facts = {
            "schema": "task038.v17.mumps-solve.v1",
            "resource_preflight": "passed",
            "predicted_peak_bytes": predicted_peak_bytes,
            "hard_limit_bytes": hard_limit_bytes,
            "analysis_only": False,
            "numeric_factor_called": True,
            "solve_called": True,
            "symbolic_calls": factor.symbolic_calls,
            "numeric_calls": factor.numeric_calls,
            "solve_calls": factor.solve_calls,
            "solution": _vector_facts(solution),
            "raw_info_after_numeric": factor.info(),
        }
        return solution, facts
    except Exception:
        _destroy(solution)
        raise


def build_p3_physical_diagnostic_matrix(
    setup: Mapping[str, Any],
    cfg: Any,
    comm: Any,
    *,
    mode_inventory: tuple[Any, Any, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Assemble the one-shot p3 physical matrix used only by Oracle A.

    The volume part is assembled from the same split curl/mass UFL form used
    by the matrix-free action.  The streaming DtN part is inserted from the
    already validated owner-local carrier, so this diagnostic has an explicit
    AIJ while production remains matrix-free.  The current MUMPS oracle is
    deliberately MPI1-only; no numeric payload is gathered.
    """

    from dolfinx import fem
    import dolfinx_mpc
    import ufl
    from petsc4py import PETSc

    from .common_3d_forms import _build_physical_volume_terms
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_carrier_from_surface,
    )
    from .fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if int(comm.size) != 1:
        raise ValueError("the exact p3 diagnostic matrix is fixed to MPI1")
    space = setup["spaces"][3]
    floquet = setup["floquets"][3]
    if getattr(floquet, "mpc", None) is None:
        raise ValueError("p3 diagnostic matrix requires finalized MPC")
    if mode_inventory is None:
        mode_inventory = build_dynamic_mode_inventory(cfg)
    modes, _mode_rows, mode_sha = mode_inventory
    modes = tuple(modes)
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _surface_assemblers(
        space,
        setup["mesh_data"],
        cfg,
        qdegree,
        jit_options=SAME_MESH_JIT_OPTIONS,
    )
    carrier = None
    matrix = None
    dtn_matrix = None
    try:
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes, assemblers, floquet.mpc, cfg
        )
        u = ufl.TrialFunction(space)
        v = ufl.TestFunction(space)
        dx = ufl.Measure(
            "dx",
            domain=setup["mesh_data"].mesh,
            subdomain_data=setup["mesh_data"].cell_tags,
        )
        curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
        compiled = fem.form(
            curl_curl + material_mass,
            jit_options=dict(SAME_MESH_JIT_OPTIONS),
        )
        matrix = dolfinx_mpc.assemble_matrix(compiled, floquet.mpc, bcs=[])
        matrix.assemble()
        rows = int(matrix.getSize()[0])
        dtn_matrix = PETSc.Mat().createAIJ([rows, rows], comm=comm)
        dtn_matrix.setUp()
        for item in carrier.entries:
            if item.coupling_rows.size and item.projection_rows.size:
                values = (
                    item.coupling_values[:, None]
                    * item.projection_values[None, :]
                    / item.normalization_h
                )
                dtn_matrix.setValues(
                    item.coupling_rows,
                    item.projection_rows,
                    values,
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        dtn_matrix.assemble()
        matrix.axpy(PETSc.ScalarType(1.0), dtn_matrix)
        info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        return matrix, {
            "schema": "task038.v17.p3-physical-diagnostic-matrix.v1",
            "operator": "same_split_volume_plus_streaming_dtn",
            "degree": 3,
            "mode_count": int(len(modes)),
            "mode_manifest_sha256": str(mode_sha),
            "dtn_quadrature_degree": int(qdegree),
            "static_condensation_used": False,
            "diagnostic_global_aij": True,
            "production_global_aij": False,
            "numeric_allgather": False,
            "rows": rows,
            "global_nnz": int(info.get("nz_used", 0)),
        }
    except Exception:
        if matrix is not None:
            matrix.destroy()
        raise
    finally:
        if dtn_matrix is not None:
            dtn_matrix.destroy()
        del assemblers
        del carrier


__all__ = (
    "ORACLE_A_PARENT_HARD_BYTES",
    "ORACLE_A_PARENT_WARNING_BYTES",
    "ORACLE_A_RESIDUAL_LIMIT",
    "ORACLE_A_RHO3_LIMIT",
    "ORACLE_A_RHO_REF_LIMIT",
    "analyze_mumps_p3",
    "build_p3_physical_diagnostic_matrix",
    "solve_mumps_p3",
)
