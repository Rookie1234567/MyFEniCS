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
import os
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
        transpose = getattr(library, "MatSolveTranspose", None)
        if transpose is not None:
            transpose.argtypes = [void, void, void]
            transpose.restype = ctypes.c_int
        library.MatDestroy.argtypes = [ctypes.POINTER(void)]
        library.MatDestroy.restype = ctypes.c_int
        library.ISDestroy.argtypes = [ctypes.POINTER(void)]
        library.ISDestroy.restype = ctypes.c_int
        library.MatMumpsGetInfog.argtypes = [void, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        library.MatMumpsGetInfog.restype = ctypes.c_int
        library.MatMumpsGetRinfog.argtypes = [void, ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        library.MatMumpsGetRinfog.restype = ctypes.c_int
        for name, pointer in (
            ("MatMumpsGetInfo", ctypes.POINTER(ctypes.c_int)),
            ("MatMumpsGetRinfo", ctypes.POINTER(ctypes.c_double)),
            ("MatMumpsGetIcntl", ctypes.POINTER(ctypes.c_int)),
            ("MatMumpsGetCntl", ctypes.POINTER(ctypes.c_double)),
        ):
            function = getattr(library, name, None)
            if function is not None:
                function.argtypes = [void, ctypes.c_int, pointer]
                function.restype = ctypes.c_int
        library.MatMumpsSetIcntl.argtypes = [void, ctypes.c_int, ctypes.c_int]
        library.MatMumpsSetIcntl.restype = ctypes.c_int
        set_cntl = getattr(library, "MatMumpsSetCntl", None)
        if set_cntl is not None:
            set_cntl.argtypes = [void, ctypes.c_int, ctypes.c_double]
            set_cntl.restype = ctypes.c_int
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

    def set_memory_limit_mb(self, megabytes: int) -> None:
        """Set MUMPS ICNTL(23) before numeric factorization (explicit opt-in)."""
        if int(megabytes) <= 0:
            raise ValueError("MUMPS memory limit must be positive and precede numeric factorization")
        self.set_icntl(23, megabytes)

    def get_icntl(self, index: int) -> int:
        """Read one public PETSc/MUMPS integer control from a live factor."""
        if self.destroyed:
            raise RuntimeError("MUMPS ICNTL read requires a live factor")
        index = int(index)
        if index <= 0:
            raise ValueError("MUMPS ICNTL index must be positive")
        function = getattr(self._api, "MatMumpsGetIcntl", None)
        if function is None:
            raise RuntimeError("MatMumpsGetIcntl is unavailable in the loaded PETSc API")
        value = ctypes.c_int()
        _petsc_error(
            function(self._handle, index, ctypes.byref(value)),
            f"MatMumpsGetIcntl({index})",
        )
        return int(value.value)

    def try_get_icntl(self, index: int) -> dict[str, Any]:
        """Read a public integer control without hiding unsupported-interface errors."""
        if self.destroyed:
            raise RuntimeError("MUMPS ICNTL read requires a live factor")
        index = int(index)
        if index <= 0:
            raise ValueError("MUMPS ICNTL index must be positive")
        function = getattr(self._api, "MatMumpsGetIcntl", None)
        if function is None:
            return {
                "index": index, "supported": False, "value": None,
                "error_code": None, "error": "MatMumpsGetIcntl unavailable",
            }
        value = ctypes.c_int()
        code = int(function(
            self._handle, index, ctypes.byref(value)))
        return {
            "index": index,
            "supported": code == 0,
            "value": int(value.value) if code == 0 else None,
            "error_code": code if code != 0 else None,
        }

    def set_icntl(self, index: int, value: int) -> None:
        """Set one public PETSc/MUMPS integer control before numeric factorization."""
        if self.destroyed or self.numeric_calls:
            raise RuntimeError("MUMPS ICNTL write requires a live pre-numeric factor")
        index, value = int(index), int(value)
        if index <= 0:
            raise ValueError("MUMPS ICNTL index must be positive")
        _petsc_error(
            self._api.MatMumpsSetIcntl(self._handle, index, value),
            f"MatMumpsSetIcntl({index})",
        )

    def get_cntl(self, index: int) -> float:
        """Read one public PETSc/MUMPS real control from a live factor."""

        if self.destroyed:
            raise RuntimeError("MUMPS CNTL read requires a live factor")
        index = int(index)
        if index <= 0:
            raise ValueError("MUMPS CNTL index must be positive")
        function = getattr(self._api, "MatMumpsGetCntl", None)
        if function is None:
            raise RuntimeError("MatMumpsGetCntl is unavailable in the loaded PETSc API")
        value = ctypes.c_double()
        _petsc_error(
            function(self._handle, index, ctypes.byref(value)),
            f"MatMumpsGetCntl({index})",
        )
        return float(value.value)

    def try_get_cntl(self, index: int) -> dict[str, Any]:
        """Read one real control while retaining an unsupported-interface code."""

        if self.destroyed:
            raise RuntimeError("MUMPS CNTL read requires a live factor")
        index = int(index)
        if index <= 0:
            raise ValueError("MUMPS CNTL index must be positive")
        function = getattr(self._api, "MatMumpsGetCntl", None)
        if function is None:
            return {
                "index": index,
                "supported": False,
                "value": None,
                "error_code": None,
                "error": "MatMumpsGetCntl unavailable",
            }
        value = ctypes.c_double()
        code = int(function(self._handle, index, ctypes.byref(value)))
        return {
            "index": index,
            "supported": code == 0,
            "value": float(value.value) if code == 0 else None,
            "error_code": code if code != 0 else None,
        }

    def set_cntl(self, index: int, value: float) -> None:
        """Set one public PETSc/MUMPS real control before numeric factorization."""

        if self.destroyed or self.numeric_calls:
            raise RuntimeError("MUMPS CNTL write requires a live pre-numeric factor")
        index, value = int(index), float(value)
        if index <= 0 or not np.isfinite(value):
            raise ValueError("MUMPS CNTL index/value is invalid")
        function = getattr(self._api, "MatMumpsSetCntl", None)
        if function is None:
            raise RuntimeError("MatMumpsSetCntl is unavailable in the loaded PETSc API")
        _petsc_error(
            function(self._handle, index, value),
            f"MatMumpsSetCntl({index})",
        )

    def public_backend_facts(self) -> dict[str, Any]:
        """Return link-level facts without reading private MUMPS structures.

        The PETSc public API does not expose the Fortran ``version_number``
        field.  The linked SONAME and available public entry points are still
        useful provenance; a caller that needs the exact MUMPS release must
        bind it to the local package/header probe in its run manifest.
        """

        petsc_name = getattr(self._api, "_name", None)
        petsc_soname = ctypes.util.find_library("petsc_complex")
        petsc_path = petsc_name if petsc_name and os.path.isabs(petsc_name) else None
        mumps_soname = ctypes.util.find_library("zmumps")
        return {
            "petsc_library_identifier": petsc_name,
            "petsc_library_soname": petsc_soname,
            "petsc_library_path": petsc_path,
            "mumps_library_soname": mumps_soname,
            "mumps_version_public_api": "not_exposed",
            "local_mumps_control_boundary": {
                "reserved_icntl": "41-48",
                "adaptive_precision_storage_control": "not_supported_by_local_public_controls",
            },
            "public_symbols": {
                name: hasattr(self._api, name)
                for name in (
                    "MatMumpsGetIcntl",
                    "MatMumpsSetIcntl",
                    "MatMumpsGetCntl",
                    "MatMumpsSetCntl",
                    "MatMumpsGetInfog",
                    "MatMumpsGetRinfog",
                )
            },
        }

    def solve(self, rhs: Any, solution: Any) -> None:
        if self.destroyed or self.numeric_calls != 1 or self.solve_calls:
            raise RuntimeError("MUMPS solve has an invalid lifecycle")
        self.solve_repeated(rhs, solution)

    def refinement_settings(self) -> dict:
        """Read the existing MUMPS internal refinement controls without changing them."""
        integer, real = ctypes.c_int(), ctypes.c_double()
        for name, value, index in (('MatMumpsGetIcntl', integer, 10),
                                   ('MatMumpsGetCntl', real, 2)):
            function = getattr(self._api, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(type(value))]
            function.restype = ctypes.c_int
            _petsc_error(function(self._handle, index, ctypes.byref(value)), name)
        return {'ICNTL(10)': integer.value, 'CNTL(2)': real.value, 'modified': False}

    def symbolic_memory_settings(self) -> dict:
        """Read controls relevant to interpreting symbolic memory, without setting them."""
        result={}
        for index in (7,10,14,18,22,23):
            result[str(index)] = self.get_icntl(index)
        return dict(icntl=result,modified=False)

    def solve_repeated(self, rhs: Any, solution: Any) -> None:
        """Apply an already qualified factor; preserve the one-shot solve API."""
        if self.destroyed or self.numeric_calls != 1:
            raise RuntimeError("MUMPS repeated solve requires a live numeric factor")
        _petsc_error(
            self._api.MatSolve(
                self._handle, _petsc_handle(rhs), _petsc_handle(solution)
            ),
            "MatSolve",
        )
        self.solve_calls += 1

    def solve_adjoint(self, rhs: Any, solution: Any) -> None:
        """Solve ``A.H x = rhs`` through this same factor.

        PETSc exposes a transpose solve, so conjugating both sides gives
        ``A.T conj(x) = conj(rhs)``.  This keeps the one-factor invariant and
        does not create a second numeric factor for adjoint tests/actions.
        """
        if self.destroyed or self.numeric_calls != 1:
            raise RuntimeError("MUMPS adjoint solve requires a live numeric factor")
        transpose = getattr(self._api, "MatSolveTranspose", None)
        if transpose is None:
            raise RuntimeError("PETSc MatSolveTranspose is unavailable")
        conjugated_rhs = rhs.duplicate()
        conjugated_solution = solution.duplicate()
        try:
            conjugated_rhs.array[:] = np.conj(rhs.array)
            _petsc_error(
                transpose(
                    self._handle,
                    _petsc_handle(conjugated_rhs),
                    _petsc_handle(conjugated_solution),
                ),
                "MatSolveTranspose",
            )
            solution.array[:] = np.conj(conjugated_solution.array)
            self.solve_calls += 1
        finally:
            _destroy(conjugated_rhs)
            _destroy(conjugated_solution)

    def info(self, extra_indices: tuple[int, ...] = (), *, include_local: bool = False) -> dict[str, Any]:
        infog: dict[str, int] = {}
        rinfog: dict[str, float] = {}
        infog_errors: dict[str, int] = {}
        rinfog_errors: dict[str, int] = {}
        for index in (*range(1, 21), *extra_indices):
            value = ctypes.c_int()
            code = self._api.MatMumpsGetInfog(self._handle, index, ctypes.byref(value))
            if int(code) != 0:
                infog_errors[str(index)] = int(code)
                continue
            infog[str(index)] = int(value.value)
        for index in range(1, 21):
            value = ctypes.c_double()
            code = self._api.MatMumpsGetRinfog(self._handle, index, ctypes.byref(value))
            if int(code) != 0:
                rinfog_errors[str(index)] = int(code)
                continue
            rinfog[str(index)] = float(value.value)
        result: dict[str, Any] = {"infog": infog, "rinfog": rinfog}
        if infog_errors:
            result["infog_errors"] = infog_errors
        if rinfog_errors:
            result["rinfog_errors"] = rinfog_errors
        if include_local:
            info: dict[str, int] = {}
            rinfo: dict[str, float] = {}
            info_function = getattr(self._api, "MatMumpsGetInfo", None)
            rinfo_function = getattr(self._api, "MatMumpsGetRinfo", None)
            if info_function is None or rinfo_function is None:
                result.update(info=None, rinfo=None, local_info_supported=False)
            else:
                local_info_errors: dict[str, int] = {}
                local_rinfo_errors: dict[str, int] = {}
                for index in range(1, 21):
                    value = ctypes.c_int()
                    code = info_function(self._handle, index, ctypes.byref(value))
                    if int(code) != 0:
                        local_info_errors[str(index)] = int(code)
                        continue
                    info[str(index)] = int(value.value)
                for index in range(1, 21):
                    value = ctypes.c_double()
                    code = rinfo_function(self._handle, index, ctypes.byref(value))
                    if int(code) != 0:
                        local_rinfo_errors[str(index)] = int(code)
                        continue
                    rinfo[str(index)] = float(value.value)
                result.update(
                    info=info,
                    rinfo=rinfo,
                    local_info_supported=True,
                    local_info_errors=local_info_errors,
                    local_rinfo_errors=local_rinfo_errors,
                )
        return result

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


MUMPS_BLR_V16_CONTROLS: dict[str, dict[int, int | float]] = {
    "icntl": {
        10: 0,
        22: 0,
        31: 0,
        32: 0,
        35: 2,
        37: 0,
    },
    "cntl": {7: 1.0e-5},
}
MUMPS_BLR_V16_DEFAULT_ICNTL = (36, 38, 39)
MUMPS_BLR_V16_TRACE_ICNTL = (
    6, 7, 8, 10, 14, 18, 22, 23, 28, 29, 31, 32, 35, 36, 37, 38, 39, 49
)
MUMPS_BLR_V16_TRACE_CNTL = (1, 3, 4, 7)


class MumpsBLRFactor(_MumpsFactor):
    """Explicit opt-in MUMPS BLR factor for the Review V16 p4 candidate.

    The ordinary ``_MumpsFactor`` path remains unchanged.  This subclass
    makes the one reviewed BLR configuration a separate lifecycle: every
    control is read/set through PETSc's public API before symbolic analysis,
    every required value is read back, and symbolic analysis refuses to start
    until that handshake has completed.
    """

    profile = "physical_p4_blr_bal_h_v16"

    def __init__(self, matrix: Any) -> None:
        super().__init__(matrix)
        self._blr_configured = False
        self.blr_control_facts: dict[str, Any] | None = None

    def _read_icntl_bundle(self, indices: tuple[int, ...]) -> dict[str, Any]:
        return {str(index): self.try_get_icntl(index) for index in indices}

    def _read_cntl_bundle(self, indices: tuple[int, ...]) -> dict[str, Any]:
        return {str(index): self.try_get_cntl(index) for index in indices}

    def control_readback(self, *, stage: str) -> dict[str, Any]:
        """Read the complete reviewed control bundle at one lifecycle point."""

        if self.destroyed:
            raise RuntimeError("MUMPS BLR control readback requires a live factor")
        return {
            "stage": str(stage),
            "icntl": self._read_icntl_bundle(MUMPS_BLR_V16_TRACE_ICNTL),
            "cntl": self._read_cntl_bundle(MUMPS_BLR_V16_TRACE_CNTL),
        }

    @staticmethod
    def _require_readback(
        record: Mapping[str, Any], index: int, expected: int | float, *, kind: str
    ) -> None:
        item = record.get(str(index))
        if not isinstance(item, Mapping) or item.get("supported") is not True:
            raise RuntimeError(
                f"MUMPS BLR {kind}({index}) public readback is unavailable: {item}"
            )
        actual = item.get("value")
        if kind == "CNTL":
            matches = np.isclose(float(actual), float(expected), rtol=0.0, atol=1.0e-15)
        else:
            matches = type(actual) is int and int(actual) == int(expected)
        if not matches:
            raise RuntimeError(
                f"MUMPS BLR {kind}({index}) readback {actual!r} != {expected!r}"
            )

    def configure_blr(self) -> dict[str, Any]:
        """Apply and verify the single frozen Review V16 BLR configuration.

        ``ICNTL(36/38/39)`` are deliberately not written.  Their local
        defaults are captured so the run manifest can freeze the backend's
        estimate inputs.  PETSc 3.19 exposes only MUMPS ``ICNTL(1..38)`` via
        its public getter, so an unsupported ``ICNTL(39)`` is retained as an
        explicit unavailable field rather than guessed from a private struct.
        """

        if self.destroyed or self.symbolic_calls or self.numeric_calls:
            raise RuntimeError("MUMPS BLR controls must be configured before symbolic analysis")
        if self._blr_configured:
            raise RuntimeError("MUMPS BLR controls may be configured only once")
        defaults = self._read_icntl_bundle(
            tuple(dict.fromkeys((*MUMPS_BLR_V16_TRACE_ICNTL, *MUMPS_BLR_V16_DEFAULT_ICNTL)))
        )
        cntl_before = self._read_cntl_bundle(MUMPS_BLR_V16_TRACE_CNTL)

        for index, value in MUMPS_BLR_V16_CONTROLS["icntl"].items():
            self.set_icntl(index, int(value))
        for index, value in MUMPS_BLR_V16_CONTROLS["cntl"].items():
            self.set_cntl(index, float(value))

        after = self._read_icntl_bundle(MUMPS_BLR_V16_TRACE_ICNTL)
        cntl_after = self._read_cntl_bundle(MUMPS_BLR_V16_TRACE_CNTL)
        for index, value in MUMPS_BLR_V16_CONTROLS["icntl"].items():
            self._require_readback(after, index, value, kind="ICNTL")
        for index, value in MUMPS_BLR_V16_CONTROLS["cntl"].items():
            self._require_readback(cntl_after, index, value, kind="CNTL")

        # The reviewed Q1 ordering, pivot and distributed-input controls are
        # inherited, not silently changed by the BLR opt-in.
        for index in (6, 7, 8, 14, 18, 28, 29):
            before_item = defaults[str(index)]
            after_item = after[str(index)]
            if before_item != after_item:
                raise RuntimeError(
                    f"MUMPS BLR changed inherited ICNTL({index}): "
                    f"{before_item} -> {after_item}"
                )
        for index in (1, 3, 4):
            before_item = cntl_before[str(index)]
            after_item = cntl_after[str(index)]
            if before_item != after_item:
                raise RuntimeError(
                    f"MUMPS BLR changed inherited CNTL({index}): "
                    f"{before_item} -> {after_item}"
                )
        self.blr_control_facts = {
            "schema": "task039extra.v16.mumps-blr-controls.v1",
            "profile": self.profile,
            "configured_before_symbolic": True,
            "requested": {
                "icntl": {str(k): int(v) for k, v in MUMPS_BLR_V16_CONTROLS["icntl"].items()},
                "cntl": {str(k): float(v) for k, v in MUMPS_BLR_V16_CONTROLS["cntl"].items()},
            },
            "defaults_before": defaults,
            "cntl_before": cntl_before,
            "effective_after": after,
            "cntl_after": cntl_after,
            "public_initial_state_is_pre_symbolic": True,
            "default_controls_frozen": {
                str(index): defaults[str(index)]
                for index in MUMPS_BLR_V16_DEFAULT_ICNTL
            },
            "icntl39_public_getter_unavailable_is_explicit": not defaults["39"]["supported"],
            "public_backend": self.public_backend_facts(),
        }
        self._blr_configured = True
        assert self.blr_control_facts is not None
        return self.blr_control_facts

    def symbolic(self, matrix: Any) -> None:
        if not self._blr_configured:
            raise RuntimeError("MUMPS BLR symbolic analysis requires pre-symbolic control setup")
        super().symbolic(matrix)
        post_symbolic = self._read_icntl_bundle(MUMPS_BLR_V16_TRACE_ICNTL)
        cntl_post_symbolic = self._read_cntl_bundle(MUMPS_BLR_V16_TRACE_CNTL)
        for index, value in MUMPS_BLR_V16_CONTROLS["icntl"].items():
            self._require_readback(post_symbolic, index, value, kind="ICNTL")
        for index, value in MUMPS_BLR_V16_CONTROLS["cntl"].items():
            self._require_readback(cntl_post_symbolic, index, value, kind="CNTL")
        if self.blr_control_facts is None:
            raise RuntimeError("MUMPS BLR control facts disappeared before symbolic readback")
        self.blr_control_facts["effective_after_symbolic"] = post_symbolic
        self.blr_control_facts["cntl_after_symbolic"] = cntl_post_symbolic
        self.blr_control_facts["default_controls_frozen"] = {
            str(index): post_symbolic[str(index)]
            for index in MUMPS_BLR_V16_DEFAULT_ICNTL
        }
        self.blr_control_facts["default_controls_frozen_phase"] = (
            "post_symbolic_public_readback"
        )
        self.blr_control_facts["icntl39_public_getter_unavailable_is_explicit"] = (
            not post_symbolic["39"]["supported"]
        )

    def numeric(self, matrix: Any) -> None:
        super().numeric(matrix)
        if self.blr_control_facts is None:
            raise RuntimeError("MUMPS BLR controls disappeared before numeric readback")
        self.blr_control_facts["effective_after_numeric"] = self.control_readback(
            stage="numeric_after"
        )

    def _record_solve_control_readback(self, solve_index: int) -> dict[str, Any]:
        if self.blr_control_facts is None:
            raise RuntimeError("MUMPS BLR controls disappeared before solve readback")
        # A solve audit is deliberately bounded: the runner owns the one
        # per-RHS record, while the factor retains only the latest readback.
        # Keeping the complete ICNTL bundle for every MatSolve would make a
        # long iterative run grow with its solve count.
        readback = {
            "stage": f"solve_{int(solve_index)}_after",
            "solve_index": int(solve_index),
            "icntl": {
                str(index): self.try_get_icntl(index) for index in (10, 35)
            },
            "cntl": {"7": self.try_get_cntl(7)},
        }
        self.blr_control_facts["solve_control_readback_latest"] = readback
        return readback

    def solve_once(self, rhs: Any, solution: Any) -> dict[str, Any]:
        """Apply one ``F_tau`` action and prove it issued one MatSolve."""

        before = int(self.solve_calls)
        self.solve_repeated(rhs, solution)
        after = int(self.solve_calls)
        if after - before != 1:
            raise RuntimeError(
                f"MUMPS BLR F_tau expected one MatSolve, observed {after - before}"
            )
        solve_control_readback = self._record_solve_control_readback(after)
        return {
            "profile": self.profile,
            "factor_solve_calls_before": before,
            "factor_solve_calls_after": after,
            "factor_solve_call_delta": after - before,
            "hidden_refinement": False,
            "controls_after_solve": solve_control_readback,
        }

    def blr_statistics(self) -> dict[str, Any]:
        """Return raw native statistics without inventing a compression ratio."""

        raw_info = self.info(
            extra_indices=(9, 21, 22, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40),
            include_local=True,
        )
        blr_field_keys = tuple(str(index) for index in (9, 29, 35, 36, 37))
        available_fields = [
            key for key in blr_field_keys if key in raw_info.get("infog", {})
        ]

        def native_entry(key: str) -> dict[str, Any] | None:
            value = raw_info.get("infog", {}).get(key)
            if type(value) is not int:
                return None
            if value < 0:
                return {
                    "raw": int(value),
                    "value": float(-value) * 1_000_000.0,
                    "unit": "entries",
                    "encoding": "negative_millions",
                }
            return {
                "raw": int(value),
                "value": float(value),
                "unit": "entries",
                "encoding": "integer",
            }

        native_compression = {
            "infog9_actual_storage_entries": native_entry("9"),
            "infog29_theoretical_entries": native_entry("29"),
            "infog35_effective_entries": native_entry("35"),
            "infog36_blr_symbolic_max_mb": raw_info.get("infog", {}).get("36"),
            "infog37_blr_symbolic_sum_mb": raw_info.get("infog", {}).get("37"),
            "rinfog3_theoretical_flops": raw_info.get("rinfog", {}).get("3"),
            "rinfog14_actual_flops": raw_info.get("rinfog", {}).get("14"),
        }
        return {
            "schema": "task039extra.v16.mumps-blr-statistics.v1",
            "backend": "mumps",
            "profile": self.profile,
            "controls": self.blr_control_facts,
            "raw_info_after_numeric": raw_info,
            "compression_stats_status": (
                "RAW_NATIVE_FIELDS_AVAILABLE"
                if available_fields
                else "COMPRESSION_STATS_UNAVAILABLE"
            ),
            "blr_field_keys_checked": list(blr_field_keys),
            "blr_field_keys_available": available_fields,
            "native_compression_fields": native_compression,
            "compression_ratio": None,
            "compression_ratio_not_inferred_from_icntl38": True,
            "unknown_fields_are_not_measured": True,
        }


def configured_mumps_blr_factor(matrix: Any) -> MumpsBLRFactor:
    """Create a V16 BLR factor with controls committed before symbolic.

    This small factory is the adapter for the existing generic
    ``_prepare_factor`` lifecycle.  If the public-control handshake fails,
    the newly created PETSc factor is destroyed before the exception escapes;
    callers therefore do not need a second wrapper with a duplicate
    symbolic/numeric/solve ledger.
    """

    factor = MumpsBLRFactor(matrix)
    try:
        factor.configure_blr()
    except BaseException:
        factor.destroy()
        raise
    return factor


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


def compile_physical_diagnostic_volume(setup, cfg, degree, *, shift_weight=None,
                                      volume_quadrature_metadata=None):
    """Original split physical form, shared by sparse diagnostic assemblers."""
    from dolfinx import fem
    import ufl
    from .common_3d_forms import _build_physical_volume_terms
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    space = setup['spaces'][degree]
    u = ufl.TrialFunction(space)
    v = ufl.TestFunction(space)
    dx = ufl.Measure(
        "dx",
        domain=setup["mesh_data"].mesh,
        subdomain_data=setup["mesh_data"].cell_tags,
    )
    curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
    if volume_quadrature_metadata is not None:
        curl_curl, material_mass = tuple(
            ufl.Form(tuple(integral.reconstruct(metadata={
                **integral.metadata(), **metadata,
            }) for integral in form.integrals()))
            for form, metadata in zip((curl_curl, material_mass), volume_quadrature_metadata, strict=True)
        )
    if shift_weight is not None:
        if volume_quadrature_metadata is None:
            raise ValueError("shifted p1 assembly requires the fine integration metadata")
        material_mass += (-.5j * cfg.k0**2 * shift_weight * ufl.inner(u, v)
                          * ufl.dx(metadata=volume_quadrature_metadata[1]))
    compiled = fem.form(
        curl_curl + material_mass,
        jit_options=dict(SAME_MESH_JIT_OPTIONS),
    )
    return compiled


def build_p3_physical_diagnostic_matrix(
    setup: Mapping[str, Any],
    cfg: Any,
    comm: Any,
    *,
    mode_inventory: tuple[Any, Any, Any] | None = None,
    degree: int = 3,
    shift_weight: Any | None = None,
    volume_quadrature_metadata: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
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
    if degree not in (1, 3) or (shift_weight is not None and degree != 1):
        raise ValueError("only the old p3 oracle or bounded shifted p1 matrix is supported")
    space = setup["spaces"][degree]
    floquet = setup["floquets"][degree]
    if degree == 1 and int(space.dofmap.index_map.size_global) > 4096:
        raise ValueError("shifted p1 matrix exceeds 4096 total storage rows before assembly")
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
        compiled = compile_physical_diagnostic_volume(setup, cfg, degree,
            shift_weight=shift_weight, volume_quadrature_metadata=volume_quadrature_metadata)
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
        facts = {
            "schema": "task038.v17.p3-physical-diagnostic-matrix.v1",
            "operator": "same_split_volume_plus_streaming_dtn",
            "degree": degree,
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
        if degree == 1:
            facts.update(
                schema="physical-intermediate.bounded-p1-matrix.v1",
                shifted_auxiliary=shift_weight is not None,
                shift_sigma=0.5 if shift_weight is not None else None,
                purpose="bounded_shifted_auxiliary_bottom_factor",
                diagnostic_global_aij=False,
                production_global_aij=False,
                development_auxiliary_global_aij=True,
            )
        return matrix, facts
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
    "MumpsBLRFactor",
    "analyze_mumps_p3",
    "build_p3_physical_diagnostic_matrix",
    "configured_mumps_blr_factor",
    "solve_mumps_p3",
)
