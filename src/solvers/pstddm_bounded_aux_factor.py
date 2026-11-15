"""Explicit exact MUMPS owner for PSTDDM auxiliary sparse factors.

This opt-in owner is intended for the h10 p6 diagnostic factory only. Existing
PSTDDM/SciPy defaults are untouched. It borrows an already canonical complex CSR
without copying, checks PETSc integer ranges, then admits the sparse-to-PETSc
copy before conversion. Symbolic INFOG, the ICNTL(23) workspace budget/readback,
numeric factor, probe solves, and destruction are recorded independently.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import uuid

import numpy as np

from .bounded_mumps import PublicMumpsFactor, incore_memory_budget, load_public_shim

P6_MUMPS_TASK_LIMIT_BYTES = 64 * 2**30
PETSC_CONVERSION_VALUE_BYTES_PER_NNZ = 24
PETSC_CONVERSION_OUTSIDE_BYTES = 256 * 2**20
OBSERVATION_SLACK_BYTES = 16 * 2**20
SYMBOLIC_STAGE_RESERVE_BYTES = 512 * 2**20
BASE_MUMPS_CONTROLS = {14: 100, 24: 1, 35: 0, 22: 0}
FAILED_AUXILIARY_OWNERS: list["ExactBoundedAuxiliaryFactor"] = []


@dataclass(frozen=True)
class _RuntimePorts:
    matrix_from_csr: Callable[..., Any]
    index_dtype: Callable[[], np.dtype]
    load_shim: Callable[..., tuple[Any, dict[str, Any]]]
    factor_factory: Callable[..., Any]
    budget_function: Callable[..., dict[str, Any]]
    compiler_command: Callable[[], Any]


def csr_conversion_admission(
    nnz: int,
    observation: dict[str, Any],
    *,
    available_floor_bytes: int,
    index_conversion_bytes: int = 0,
    mumps_task_limit_bytes: int = P6_MUMPS_TASK_LIMIT_BYTES,
    future_co_resident_reserve_bytes: int = 0,
) -> dict[str, Any]:
    """Check exact sparse-to-PETSc charge before allocating conversion copies.

    The gate covers CSR conversion only. MUMPS workspace is independently
    admitted after symbolic INFOG(16) using ``incore_memory_budget``.
    """
    fields = (
        nnz, available_floor_bytes, index_conversion_bytes,
        mumps_task_limit_bytes, future_co_resident_reserve_bytes,
        observation.get("effective_cap_bytes"),
        observation.get("live_tree_and_supervisor_bytes"),
        observation.get("margin_bytes"),
        observation.get("system", {}).get("available"),
    )
    if any(type(value) is not int or value < 0 for value in fields):
        raise ValueError("exact nonnegative integer nnz/resource observations are required")
    if nnz < 1 or available_floor_bytes < 2**30 or mumps_task_limit_bytes < 2**30:
        raise ValueError("positive nnz and >=1GiB resource floors are required")
    conversion_copy_bytes = PETSC_CONVERSION_VALUE_BYTES_PER_NNZ * nnz
    conversion_charge = (
        conversion_copy_bytes + index_conversion_bytes
        + PETSC_CONVERSION_OUTSIDE_BYTES + future_co_resident_reserve_bytes
    )
    live_budget = min(
        min(observation["effective_cap_bytes"], mumps_task_limit_bytes)
        - observation["live_tree_and_supervisor_bytes"],
        observation["system"]["available"] - available_floor_bytes,
    )
    required_with_margin = conversion_charge + observation["margin_bytes"] + OBSERVATION_SLACK_BYTES
    return {
        "policy": "exact-csr-petsc-conversion-live-admission-v2",
        "matrix_stored_nnz": nnz,
        "petsc_conversion_upper_bytes": conversion_copy_bytes,
        "petsc_index_conversion_bytes": index_conversion_bytes,
        "outside_conversion_reserve_bytes": PETSC_CONVERSION_OUTSIDE_BYTES,
        "future_co_resident_reserve_bytes": future_co_resident_reserve_bytes,
        "conversion_charge_bytes": conversion_charge,
        "live_budget_after_floor_bytes": live_budget,
        "stage_margin_bytes": observation["margin_bytes"],
        "observation_slack_bytes": OBSERVATION_SLACK_BYTES,
        "required_with_margin_bytes": required_with_margin,
        "available_floor_bytes": available_floor_bytes,
        "mumps_task_limit_bytes": mumps_task_limit_bytes,
        "live_observation": observation,
        "passed": live_budget >= required_with_margin,
        "estimate_not_upper_bound": True,
        "MUMPS_workspace_not_included": True,
    }


def _borrow_canonical_csr(matrix: Any):
    from scipy import sparse

    if not sparse.isspmatrix_csr(matrix):
        raise TypeError("bounded auxiliary factor input must be a SciPy CSR matrix")
    if matrix.dtype != np.dtype("complex128"):
        raise TypeError("bounded auxiliary factor requires an existing complex128 CSR")
    if len(matrix.shape) != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 1:
        raise ValueError("bounded auxiliary factor matrix must be nonempty and square")
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise ValueError("bounded auxiliary factor borrows canonical CSR; caller must canonicalize first")
    if matrix.nnz < 1:
        raise ValueError("bounded auxiliary CSR must contain nonzero storage")
    for start in range(0, int(matrix.nnz), 65_536):
        block = matrix.data[start:start + 65_536]
        if np.any(block == 0.0) or not np.all(np.isfinite(block)):
            raise ValueError("bounded auxiliary CSR must contain finite nonzero entries only")
    return matrix


def _petsc_index_dtype() -> np.dtype:
    from petsc4py import PETSc
    return np.dtype(PETSc.IntType)


def _validate_csr_index_range(csr: Any, index_dtype: np.dtype) -> int:
    dtype = np.dtype(index_dtype)
    if not np.issubdtype(dtype, np.signedinteger):
        raise TypeError("PETSc.IntType must be a signed integer dtype")
    limit = np.iinfo(dtype).max
    nrows, ncols = (int(value) for value in csr.shape)
    nnz = int(csr.nnz)
    if max(nrows, ncols, nnz) > limit:
        raise OverflowError("CSR dimensions or nnz exceed PETSc.IntType range")
    if (csr.indptr.ndim != 1 or csr.indptr.size != nrows + 1
            or csr.indices.ndim != 1 or csr.indices.size != nnz):
        raise ValueError("CSR indptr/indices lengths do not match shape and nnz")
    if (csr.indptr.dtype.kind not in "iu" or csr.indices.dtype.kind not in "iu"
            or csr.indptr.size == 0 or int(csr.indptr[0]) != 0
            or int(csr.indptr[-1]) != nnz
            ):
        raise ValueError("CSR index arrays are malformed or out of matrix range")
    previous_pointer = 0
    for start in range(0, int(csr.indptr.size), 65_536):
        block = csr.indptr[start:start + 65_536]
        if (int(block[0]) < previous_pointer or np.any(block < 0)
                or np.any(block[1:] < block[:-1]) or np.any(block > limit)):
            raise OverflowError("CSR row pointers are nonmonotone or exceed PETSc.IntType range")
        previous_pointer = int(block[-1])
    for start in range(0, nnz, 65_536):
        block = csr.indices[start:start + 65_536]
        if np.any(block < 0) or np.any(block >= ncols) or np.any(block > limit):
            raise OverflowError("CSR column indices are invalid or exceed PETSc.IntType range")
    itemsize = dtype.itemsize
    index_copy_bytes = 0
    if np.dtype(csr.indptr.dtype) != dtype:
        index_copy_bytes += int(csr.indptr.size) * itemsize
    if np.dtype(csr.indices.dtype) != dtype:
        index_copy_bytes += int(csr.indices.size) * itemsize
    return index_copy_bytes


def _petsc_matrix_from_csr(csr: Any, *, comm: Any = None):
    from petsc4py import PETSc

    if np.dtype(PETSc.ScalarType) != np.dtype("complex128"):
        raise RuntimeError("bounded auxiliary factors require complex128 PETSc")
    target_comm = PETSc.COMM_SELF if comm is None else comm
    matrix = PETSc.Mat().createAIJ(
        size=csr.shape,
        csr=(
            np.asarray(csr.indptr, dtype=PETSc.IntType),
            np.asarray(csr.indices, dtype=PETSc.IntType),
            np.asarray(csr.data, dtype=PETSc.ScalarType),
        ),
        comm=target_comm,
    )
    matrix.assemble()
    return matrix


def _default_runtime() -> _RuntimePorts:
    from ..common.runtime_resource_policy import mumps_compiler_command

    return _RuntimePorts(
        matrix_from_csr=_petsc_matrix_from_csr,
        index_dtype=_petsc_index_dtype,
        load_shim=load_public_shim,
        factor_factory=PublicMumpsFactor,
        budget_function=incore_memory_budget,
        compiler_command=mumps_compiler_command,
    )


class ExactBoundedAuxiliaryFactor:
    """Own one exact auxiliary factor and PETSc matrix until explicitly closed.

    The input CSR is borrowed read-only and must not be mutated by its caller
    while the PETSc matrix is built. ``solve`` returns the array expected by
    the existing PC interface; its true relative residual and count are kept
    in ``audit``. No extra per-call residual threshold is imposed.
    """

    def __init__(
        self,
        csr_matrix: Any,
        *,
        observe: Callable[[str], dict[str, Any]],
        admit: Callable[..., Any],
        directory: str | Path,
        available_floor_bytes: int,
        comm: Any = None,
        mumps_task_limit_bytes: int = P6_MUMPS_TASK_LIMIT_BYTES,
        future_co_resident_reserve_bytes: int = 0,
        probe_rhs: np.ndarray | None = None,
        probe_relative_limit: float = 1e-9,
        mass_reconstruction_probe: Callable[["ExactBoundedAuxiliaryFactor"], float] | None = None,
        mass_reconstruction_relative_limit: float = 1e-10,
        runtime: _RuntimePorts | None = None,
    ) -> None:
        self._matrix = None
        self._factor = None
        self._symbolic_factor = None
        self._closed = False
        self._runtime = _default_runtime() if runtime is None else runtime
        self._observe = observe
        self._admit = admit
        self._directory = Path(directory)
        self._available_floor_bytes = int(available_floor_bytes)
        self._comm = comm
        self._mumps_task_limit_bytes = int(mumps_task_limit_bytes)
        self._future_co_resident_reserve_bytes = int(future_co_resident_reserve_bytes)
        self._probe_rhs = None if probe_rhs is None else np.asarray(probe_rhs, dtype=np.complex128)
        self._probe_relative_limit = float(probe_relative_limit)
        self._mass_reconstruction_probe = mass_reconstruction_probe
        self._mass_reconstruction_relative_limit = float(mass_reconstruction_relative_limit)
        if not np.isfinite(self._probe_relative_limit) or self._probe_relative_limit <= 0.0:
            raise ValueError("probe_relative_limit must be finite and positive")
        if (not np.isfinite(self._mass_reconstruction_relative_limit)
                or self._mass_reconstruction_relative_limit <= 0.0):
            raise ValueError("mass_reconstruction_relative_limit must be finite and positive")
        self._audit: dict[str, Any] = {
            "schema": "pstddm-exact-bounded-aux-factor.v2",
            "mumps_task_limit_bytes": self._mumps_task_limit_bytes,
            "borrowed_csr_not_copied": True,
            "probe_relative_limit": self._probe_relative_limit,
            "mass_reconstruction_relative_limit": self._mass_reconstruction_relative_limit,
            "phase_seconds": {},
            "solve_count": 0,
            "last_solve_relative_residual": None,
        }
        self._phase_started: float | None = None
        self._start_time = time.monotonic()
        try:
            self._initialize(csr_matrix)
        except BaseException as error:
            self._record_failure(error)
            try:
                self.close()
            except BaseException as cleanup_error:
                if self not in FAILED_AUXILIARY_OWNERS:
                    FAILED_AUXILIARY_OWNERS.append(self)
                error.add_note("auxiliary factor cleanup failed: " + repr(cleanup_error))
            raise

    @property
    def audit(self) -> dict[str, Any]:
        return dict(self._audit)

    @property
    def shape(self) -> tuple[int, int]:
        if self._matrix is None:
            raise RuntimeError("auxiliary factor is closed")
        return tuple(int(value) for value in self._matrix.getSize())

    def _persist_audit(self, status: str) -> None:
        self._audit["status"] = status
        self._audit["elapsed_seconds"] = time.monotonic() - self._start_time
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._directory / "auxiliary_factor_audit.json"
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps(self._audit, sort_keys=True, indent=2) + "\n",
                                 encoding="utf-8")
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _start_phase(self, name: str) -> None:
        if self._phase_started is not None:
            raise RuntimeError("previous auxiliary factor phase was not finalized")
        self._audit["phase"] = name
        self._phase_started = time.monotonic()
        self._persist_audit("running")

    def _finish_phase(self, name: str) -> None:
        if self._phase_started is None or self._audit.get("phase") != name:
            raise RuntimeError("auxiliary factor phase lifecycle mismatch")
        self._audit["phase_seconds"][name] = time.monotonic() - self._phase_started
        self._phase_started = None
        self._persist_audit("running")

    def _record_failure(self, error: BaseException) -> None:
        if self._phase_started is not None:
            name = str(self._audit.get("phase", "unknown"))
            self._audit["phase_seconds"][name] = time.monotonic() - self._phase_started
            self._phase_started = None
        self._audit["failure"] = {"type": type(error).__name__, "message": str(error)}
        try:
            self._persist_audit("failed")
        except BaseException as record_error:
            error.add_note("auxiliary factor failure audit could not be saved: " + repr(record_error))

    def _initialize(self, matrix: Any) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        self._start_phase("csr_validate_and_conversion_admission")
        csr = _borrow_canonical_csr(matrix)
        petsc_index_dtype = np.dtype(self._runtime.index_dtype())
        index_copy_bytes = _validate_csr_index_range(csr, petsc_index_dtype)
        nnz = int(csr.nnz)
        conversion_observation = self._observe("before_petsc_csr_conversion")
        conversion = csr_conversion_admission(
            nnz,
            conversion_observation,
            available_floor_bytes=self._available_floor_bytes,
            index_conversion_bytes=index_copy_bytes,
            mumps_task_limit_bytes=self._mumps_task_limit_bytes,
            future_co_resident_reserve_bytes=self._future_co_resident_reserve_bytes,
        )
        self._audit.update({
            "shape": [int(value) for value in csr.shape],
            "matrix_stored_nnz": nnz,
            "petsc_index_dtype": petsc_index_dtype.name,
            "conversion_admission": conversion,
        })
        self._persist_audit("running")
        if not conversion["passed"]:
            raise MemoryError("AUX_CSR_PETSC_CONVERSION_RESOURCE_GATE")
        self._admit(
            "auxiliary_petsc_csr_conversion",
            conversion["conversion_charge_bytes"],
            estimate_basis=conversion,
        )
        self._finish_phase("csr_validate_and_conversion_admission")

        self._start_phase("petsc_conversion")
        self._matrix = self._runtime.matrix_from_csr(csr, comm=self._comm)
        matrix_nnz = self._matrix.getInfo()["nz_used"]
        if (isinstance(matrix_nnz, bool) or not float(matrix_nnz).is_integer()
                or int(matrix_nnz) != nnz):
            raise RuntimeError("PETSc conversion changed exact stored CSR nnz")
        try:
            matrix_comm_size = int(self._matrix.getComm().getSize())
        except AttributeError:
            matrix_comm_size = 1
        if matrix_comm_size != 1:
            raise RuntimeError("exact auxiliary CSR factor owner currently requires a one-rank matrix")
        self._audit["petsc_stored_nnz"] = int(matrix_nnz)
        self._finish_phase("petsc_conversion")

        self._start_phase("mumps_shim_load")
        api, shim_identity = self._runtime.load_shim(
            self._directory,
            compiler_command=self._runtime.compiler_command(),
        )
        self._audit["shim"] = shim_identity
        self._finish_phase("mumps_shim_load")

        self._start_phase("mumps_symbolic_preflight")
        symbolic_observation = self._observe("before_auxiliary_symbolic")
        self._admit(
            "mumps_symbolic",
            SYMBOLIC_STAGE_RESERVE_BYTES,
            estimate_basis={"reserve_bytes": SYMBOLIC_STAGE_RESERVE_BYTES,
                            "observation": symbolic_observation},
        )
        self._symbolic_factor = self._runtime.factor_factory(
            self._matrix, api, controls=BASE_MUMPS_CONTROLS,
        )
        symbolic_error = None
        try:
            symbolic_info = self._symbolic_factor.symbolic()
        except BaseException as error:
            symbolic_error = error
            raise
        finally:
            try:
                self._symbolic_factor.close()
            except BaseException as cleanup_error:
                if symbolic_error is None:
                    raise
                symbolic_error.add_note("symbolic factor cleanup failed: " + repr(cleanup_error))
            else:
                self._symbolic_factor = None
        if symbolic_info["1"] < 0 or symbolic_info["16"] <= 0:
            raise RuntimeError("MUMPS symbolic INFOG failure or missing INFOG16 estimate")
        self._audit["symbolic_preflight_INFOG"] = dict(symbolic_info)
        self._finish_phase("mumps_symbolic_preflight")

        self._start_phase("mumps_numeric_budget")
        numeric_observation = self._observe("after_symbolic_release_for_numeric_budget")
        budget = self._runtime.budget_function(
            symbolic_info,
            nnz,
            numeric_observation,
            available_floor_bytes=self._available_floor_bytes,
            mumps_task_limit_bytes=self._mumps_task_limit_bytes,
            future_co_resident_reserve_bytes=self._future_co_resident_reserve_bytes,
        )
        self._audit["numeric_memory_budget"] = budget
        self._persist_audit("running")
        if not budget["passed"]:
            raise MemoryError("MUMPS_INCORE_WORKSPACE_CAP_BELOW_ANALYSIS_REQUIREMENT")
        controls = dict(BASE_MUMPS_CONTROLS)
        controls[23] = int(budget["numeric_ICNTL23_MB"])
        self._admit("mumps_numeric", int(budget["future_numeric_bytes"]),
                    estimate_basis=budget)
        self._finish_phase("mumps_numeric_budget")

        self._start_phase("mumps_numeric_factor")
        self._factor = self._runtime.factor_factory(self._matrix, api, controls=controls)
        expected_controls = {str(key): int(value) for key, value in controls.items()}
        if self._factor.controls != expected_controls:
            raise RuntimeError("MUMPS controls, including frozen ICNTL23, failed readback")
        repeated_symbolic = self._factor.symbolic()
        if repeated_symbolic["1"] < 0 or repeated_symbolic["16"] <= 0:
            raise RuntimeError("numeric-owner symbolic INFOG failure")
        if int(repeated_symbolic["16"]) > controls[23]:
            raise RuntimeError("repeated symbolic INFOG16 exceeds frozen ICNTL23 workspace cap")
        try:
            self._factor.numeric()
        except BaseException as numeric_error:
            try:
                self._audit["numeric_failure_factor_inventory"] = self._read_numeric_inventory(
                    self._factor,
                )
            except BaseException as inventory_error:
                numeric_error.add_note(
                    "numeric failure MUMPS INFOG unavailable: " + repr(inventory_error)
                )
            self._persist_audit("failed")
            raise
        self._audit["numeric_owner_controls"] = dict(self._factor.controls)
        self._audit["numeric_owner_symbolic_INFOG"] = dict(repeated_symbolic)
        self._audit["numeric_owner_factor_inventory"] = self._read_numeric_inventory(self._factor)
        self._audit["numeric_post_factor_live_observation"] = self._observe("after_mumps_numeric_factor")
        self._finish_phase("mumps_numeric_factor")

        self._start_phase("probe_and_optional_mass_reconstruction")
        rhs = self._probe_rhs
        if rhs is None:
            rhs = np.ones(int(csr.shape[0]), dtype=np.complex128)
        if rhs.ndim != 1 or rhs.size != csr.shape[0] or not np.all(np.isfinite(rhs)):
            raise ValueError("probe_rhs must be a finite vector matching the matrix")
        _probe_solution, probe_residual = self._solve_array(rhs)
        self._audit["probe_relative_residual"] = probe_residual
        if not np.isfinite(probe_residual) or probe_residual > self._probe_relative_limit:
            raise RuntimeError("MUMPS auxiliary factor probe residual exceeds limit")
        if self._mass_reconstruction_probe is not None:
            reconstruction_residual = float(self._mass_reconstruction_probe(self))
            self._audit["mass_reconstruction_relative_residual"] = reconstruction_residual
            if (not np.isfinite(reconstruction_residual)
                    or reconstruction_residual > self._mass_reconstruction_relative_limit):
                raise RuntimeError("auxiliary mass reconstruction residual exceeds limit")
        self._audit["probe_relative_limit"] = self._probe_relative_limit
        self._audit["mass_reconstruction_relative_limit"] = self._mass_reconstruction_relative_limit
        self._finish_phase("probe_and_optional_mass_reconstruction")
        self._persist_audit("ready")

    def _solve_array(self, rhs: np.ndarray) -> tuple[np.ndarray, float]:
        if self._closed or self._matrix is None or self._factor is None:
            raise RuntimeError("auxiliary factor is not numerically ready")
        rhs_vec = self._matrix.createVecRight()
        solution_vec = self._matrix.createVecRight()
        residual_vec = self._matrix.createVecLeft()
        try:
            if rhs_vec.getSize() != len(rhs):
                raise ValueError("RHS size differs from one-rank auxiliary matrix")
            rhs_vec.setArray(np.asarray(rhs, dtype=np.complex128).copy())
            self._factor.solve(rhs_vec, solution_vec)
            self._matrix.mult(solution_vec, residual_vec)
            residual_vec.axpy(-1.0, rhs_vec)
            denominator = max(float(rhs_vec.norm()), np.finfo(np.float64).tiny)
            relative_residual = float(residual_vec.norm()) / denominator
            solution = solution_vec.getArray(readonly=True).copy()
            self._audit["solve_count"] = int(self._audit["solve_count"]) + 1
            self._audit["last_solve_relative_residual"] = relative_residual
            return solution, relative_residual
        finally:
            residual_vec.destroy()
            solution_vec.destroy()
            rhs_vec.destroy()

    @staticmethod
    def _read_numeric_inventory(factor_owner: Any) -> dict[str, Any]:
        factor = getattr(factor_owner, "factor", None)
        if factor is None or not hasattr(factor, "getMumpsInfog"):
            raise RuntimeError("numeric MUMPS factor does not expose public INFOG")
        infog: dict[str, int] = {}
        for index in range(1, 41):
            try:
                infog[str(index)] = int(factor.getMumpsInfog(index))
            except Exception:
                continue
        rinfog: dict[str, float] = {}
        if hasattr(factor, "getMumpsRinfog"):
            for index in range(1, 21):
                try:
                    rinfog[str(index)] = float(factor.getMumpsRinfog(index))
                except Exception:
                    continue
        raw_nnz = infog.get("9")
        corrected_nnz = (
            None if raw_nnz is None else raw_nnz if raw_nnz >= 0 else abs(raw_nnz) * 1_000_000
        )
        return {
            "mumps_raw_infog": infog,
            "mumps_raw_rinfog": rinfog,
            "factor_nnz_corrected": corrected_nnz,
            "factor_nnz_corrected_source": (
                ("mumps_infog_9_direct" if raw_nnz is not None and raw_nnz >= 0
                 else "mumps_infog_9_negative_millions" if raw_nnz is not None else None)
            ),
        }

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        """Solve one RHS and return only the solution array for PC compatibility."""
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim != 1 or values.size != self.shape[0] or not np.all(np.isfinite(values)):
            raise ValueError("rhs must be a finite vector matching the auxiliary matrix")
        solution, _relative_residual = self._solve_array(values)
        return solution

    def solve_checked(
        self,
        rhs: np.ndarray,
        *,
        relative_limit: float | None = None,
    ) -> tuple[np.ndarray, float]:
        """Solve and measure true residual; limit is optional and caller-owned."""
        if relative_limit is not None and (
            not np.isfinite(relative_limit) or relative_limit <= 0.0
        ):
            raise ValueError("relative_limit must be finite and positive when supplied")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.ndim != 1 or values.size != self.shape[0] or not np.all(np.isfinite(values)):
            raise ValueError("rhs must be a finite vector matching the auxiliary matrix")
        solution, residual = self._solve_array(values)
        if relative_limit is not None and (not np.isfinite(residual) or residual > relative_limit):
            raise RuntimeError("MUMPS auxiliary solve residual exceeds caller limit")
        return solution, residual

    def close(self) -> None:
        """Destroy factor owners and matrix, retaining references on cleanup error."""
        if self._closed:
            return
        errors: list[BaseException] = []
        owner_cleanup_failed = False
        for attr in ("_symbolic_factor", "_factor"):
            owner = getattr(self, attr)
            if owner is not None:
                try:
                    owner.close()
                except BaseException as error:
                    errors.append(error)
                    owner_cleanup_failed = True
                else:
                    setattr(self, attr, None)
        if self._matrix is not None and not owner_cleanup_failed:
            try:
                self._matrix.destroy()
            except BaseException as error:
                errors.append(error)
            else:
                self._matrix = None
        self._closed = self._symbolic_factor is None and self._factor is None and self._matrix is None
        if errors:
            if self not in FAILED_AUXILIARY_OWNERS:
                FAILED_AUXILIARY_OWNERS.append(self)
            primary = errors[0]
            for extra in errors[1:]:
                primary.add_note("additional auxiliary cleanup failure: " + repr(extra))
            try:
                self._audit["cleanup_failure"] = [repr(error) for error in errors]
                self._persist_audit("cleanup_failed")
            except BaseException as record_error:
                primary.add_note("cleanup failure audit could not be saved: " + repr(record_error))
            raise primary
        self._audit["cleanup_status"] = "closed"
        try:
            self._persist_audit("failed" if self._audit.get("status") == "failed" else "closed")
        except BaseException as record_error:
            if self not in FAILED_AUXILIARY_OWNERS:
                FAILED_AUXILIARY_OWNERS.append(self)
            raise RuntimeError("auxiliary factor closed but cleanup audit could not be saved") from record_error

    def __enter__(self) -> "ExactBoundedAuxiliaryFactor":
        if self._closed:
            raise RuntimeError("auxiliary factor is closed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            self.close()
        except BaseException as cleanup_error:
            if exc is None:
                raise
            exc.add_note("auxiliary factor cleanup failed: " + repr(cleanup_error))
        return False
