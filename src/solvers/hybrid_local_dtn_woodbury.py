"""Exact dynamic-mode DtN Woodbury action over borrowed local components."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .condensed_dtn import gather_small_petsc_matrix
from .common_3d_solve import _petsc_factor_inventory, _petsc_matrix_stats


HYBRID_DTN_WOODBURY_MODE_COUNT = 40
MUMPS_BLR_V5_H4_PROFILE = "mumps_blr_v5_h4"
MUMPS_BLR_V5_H4_1E3_PROFILE = "mumps_blr_v5_h4_1e3"
MUMPS_EXACT_WORKSPACE_RELAXATION_PERCENT = 40

__all__ = (
    "HYBRID_DTN_WOODBURY_MODE_COUNT",
    "MUMPS_BLR_V5_H4_PROFILE",
    "MUMPS_BLR_V5_H4_1E3_PROFILE",
    "mumps_blr_v5_h4_controls",
    "HybridLocalDtnWoodburyOracle",
    "HybridLocalDtnWoodburyFixedAction",
    "ResearchExactFactorInverse",
    "ResearchExactSideLuAction",
    "create_research_exact_side_lu_action",
    "HybridLocalDtnWoodburyFixedBudgetKrylovAction",
)


def _max_over_comm(comm: MPI.Comm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _gather_owned_small_vector(vector: PETSc.Vec) -> np.ndarray:
    """Replicate a small distributed vector without using matrix columns."""

    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather((first, last, local))
    values = np.empty(int(vector.getSize()), dtype=np.complex128)
    for packet_first, packet_last, packet_values in packets:
        values[packet_first:packet_last] = packet_values
    return values


def _set_owned_small_vector(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def mumps_blr_v5_h4_controls(profile: str) -> dict[str, float | int]:
    if profile == MUMPS_BLR_V5_H4_PROFILE:
        cntl_7 = 1.0e-5
    elif profile == MUMPS_BLR_V5_H4_1E3_PROFILE:
        cntl_7 = 1.0e-3
    else:
        raise ValueError(f"Unsupported compressed factor profile: {profile}")
    return {"icntl_35": 1, "cntl_7": cntl_7, "icntl_14": 80}


def _configure_v5_blr_factor(pc: PETSc.PC, profile: str | None) -> PETSc.Mat | None:
    if profile is None:
        return None
    controls = mumps_blr_v5_h4_controls(profile)
    pc.setFactorSetUpSolverType()
    factor = pc.getFactorMatrix()
    factor.setMumpsIcntl(35, controls["icntl_35"])
    factor.setMumpsCntl(7, controls["cntl_7"])
    factor.setMumpsIcntl(14, controls["icntl_14"])
    return factor


class HybridLocalDtnWoodburyOracle:
    """Exact mode-count-preserving Woodbury action over borrowed components."""

    def __init__(
        self,
        base_inverse: Any,
        components: Any,
        *,
        base_identity: str = "exact_F_direct",
        compact_storage: bool = False,
        streaming_w_batch_size: int | None = None,
    ) -> None:
        self.base_inverse = base_inverse
        self.components = components
        self.F = components.F
        self.C = components.C
        self.D = components.D
        self.H = components.H
        self.base_identity = str(base_identity)
        self._compact_storage = bool(compact_storage)
        if streaming_w_batch_size is not None:
            streaming_w_batch_size = int(streaming_w_batch_size)
            if streaming_w_batch_size not in (8, 16, 32):
                raise ValueError("Streaming-W batch size must be one of 8, 16, or 32")
            if not self._compact_storage:
                raise ValueError(
                    "Streaming-W storage requires compact factor-only storage"
                )
        self._streaming_w_batch_size = streaming_w_batch_size
        self._factor_only_storage = bool(
            getattr(base_inverse, "factor_only_storage", False)
        )
        self.comm = self.F.getComm().tompi4py()
        self._source_size = int(self.F.getSize()[1])
        self._target_size = int(self.F.getSize()[0])
        self._operator = self.F
        self.n_aux = int(self.H.getSize()[0])
        if self.n_aux <= 0 or self.H.getSize() != (self.n_aux, self.n_aux):
            raise ValueError("Woodbury oracle requires a non-empty square modal block")
        if self.C.getSize() != (self.F.getSize()[0], self.n_aux):
            raise ValueError("borrowed C has incompatible active/modal dimensions")
        if self.D.getSize() != (self.n_aux, self.F.getSize()[0]):
            raise ValueError("borrowed D has incompatible modal/active dimensions")
        if self.F.getSize()[0] != self.D.getSize()[1]:
            raise ValueError("borrowed F and D have incompatible active dimensions")
        if not hasattr(base_inverse, "solve"):
            raise TypeError("Woodbury base inverse must expose solve(source, target)")

        self._destroyed = False
        self._z = self.F.createVecLeft()
        self._d_work = self.D.createVecLeft()
        self._W_local: np.ndarray | None = None
        self._C_action: PETSc.Mat | None = None
        self._C_input: PETSc.Vec | None = None
        self._C_response: PETSc.Vec | None = None
        self._correction: PETSc.Vec | None = None
        self._C_action_owned = False
        self._K: np.ndarray | None = None
        self._lu: np.ndarray | None = None
        self._piv: np.ndarray | None = None
        self._K_rank: int | None = None
        self._K_condition: float | None = None
        self._K_shape: list[int] | None = None
        self._K_nbytes: int | None = None
        self._K_dtype = "complex128"
        self._lu_shape: list[int] | None = None
        self._piv_shape: list[int] | None = None
        self._lu_nbytes: int | None = None
        self._piv_nbytes: int | None = None
        self._K_released = False
        self._F_C_H_references_released = False
        self._F_C_H_matrices_released = False
        self._F_H_released = False
        self._F_H_matrices_released = False
        self._borrowed_component_handles_released = False
        self._D_retained = True
        self._arrays_finite = False
        self._last_failure_audit: dict[str, Any] | None = None
        self._setup_seconds = 0.0
        self._setup_factor_solve_count = 0
        self._setup_d_apply_count = 0
        self._streaming_w_batch_peak_bytes = 0
        self._streaming_w_batch_local_peak_bytes = 0
        self._apply_base_solve_count = 0
        self._apply_d_count = 0
        self._apply_c_count = 0
        self._apply_seconds = 0.0
        self.apply_count = 0
        self._build()

    def _build(self) -> None:
        started = perf_counter()
        H_dense = np.asarray(gather_small_petsc_matrix(self.H), dtype=np.complex128)
        local_rows = int(self.F.getLocalSize()[0])
        streaming = self._streaming_w_batch_size is not None
        W_local = (
            None
            if streaming
            else np.empty((local_rows, self.n_aux), dtype=np.complex128)
        )
        D_times_W = np.empty((self.n_aux, self.n_aux), dtype=np.complex128)
        modal_basis = self.C.createVecRight()
        c_column = self.C.createVecLeft()
        w_column = self.F.createVecLeft()
        d_column = self.D.createVecLeft()
        try:
            first, last = (int(value) for value in modal_basis.getOwnershipRange())
            batch_size = self._streaming_w_batch_size or self.n_aux
            for batch_start in range(0, self.n_aux, batch_size):
                batch_width = min(batch_size, self.n_aux - batch_start)
                response_batch = (
                    np.empty((local_rows, batch_width), dtype=np.complex128)
                    if streaming
                    else None
                )
                for offset in range(batch_width):
                    column = batch_start + offset
                    modal_basis.set(0.0)
                    if first <= column < last:
                        modal_basis.getArray()[column - first] = PETSc.ScalarType(1.0)
                    modal_basis.assemble()
                    self.C.mult(modal_basis, c_column)
                    self.base_inverse.solve(c_column, w_column)
                    self._setup_factor_solve_count += 1
                    response = np.asarray(
                        w_column.getArray(readonly=True), dtype=np.complex128
                    )
                    if response_batch is None:
                        W_local[:, column] = response
                    else:
                        response_batch[:, offset] = response
                    if response_batch is None:
                        self.D.mult(w_column, d_column)
                        self._setup_d_apply_count += 1
                        D_times_W[:, column] = _gather_owned_small_vector(d_column)
                if response_batch is not None:
                    for offset in range(batch_width):
                        w_column.getArray()[:] = response_batch[:, offset]
                        self.D.mult(w_column, d_column)
                        self._setup_d_apply_count += 1
                        D_times_W[:, batch_start + offset] = _gather_owned_small_vector(
                            d_column
                        )
                if response_batch is not None:
                    self._streaming_w_batch_peak_bytes = max(
                        self._streaming_w_batch_peak_bytes,
                        int(response_batch.nbytes),
                    )
                    del response_batch
            if streaming:
                self._streaming_w_batch_local_peak_bytes = int(
                    self._streaming_w_batch_peak_bytes
                )
                self._streaming_w_batch_peak_bytes = int(
                    _max_over_comm(self.comm, self._streaming_w_batch_peak_bytes)
                )
        finally:
            d_column.destroy()
            w_column.destroy()
            c_column.destroy()
            modal_basis.destroy()

        K = H_dense - D_times_W
        singular_values = np.linalg.svd(K, compute_uv=False)
        if singular_values.size == 0 or not np.all(np.isfinite(singular_values)):
            raise RuntimeError("Woodbury K SVD is not finite")
        scale = float(singular_values[0])
        rank_tolerance = np.finfo(np.float64).eps * max(K.shape) * scale
        rank = int(np.count_nonzero(singular_values > rank_tolerance))
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values[-1] > 0.0
            else float("inf")
        )
        lu, piv = lu_factor(K, check_finite=True)
        local_arrays_finite = bool(
            np.all(np.isfinite(H_dense))
            and (W_local is None or np.all(np.isfinite(W_local)))
            and np.all(np.isfinite(D_times_W))
            and np.all(np.isfinite(K))
            and np.all(np.isfinite(lu))
            and np.all(np.isfinite(piv))
        )
        self._arrays_finite = bool(
            self.comm.allreduce(local_arrays_finite, op=MPI.LAND)
        )
        self._W_local = W_local
        self._K = K
        self._K_shape = list(K.shape)
        self._K_nbytes = int(K.nbytes)
        self._lu = np.asarray(lu, dtype=np.complex128)
        self._piv = np.asarray(piv, dtype=np.int32)
        self._lu_shape = list(self._lu.shape)
        self._piv_shape = list(self._piv.shape)
        self._lu_nbytes = int(self._lu.nbytes)
        self._piv_nbytes = int(self._piv.nbytes)
        self._K_rank = rank
        self._K_condition = condition
        self._setup_seconds = _max_over_comm(
            self.comm,
            perf_counter() - started,
        )
        if self._compact_storage:
            self._operator = getattr(self.base_inverse, "operator", None)
            if self._operator is None:
                raise ValueError(
                    "Compact Woodbury storage requires a retained factor operator"
                )
            if self._streaming_w_batch_size is not None:
                if getattr(self.components, "C", None) is not self.C:
                    raise ValueError(
                        "Streaming-W storage requires components.C ownership"
                    )
                self._C_action = self.C
                self._C_action_owned = True
                self.components.C = None
                self.C = None
                self._C_input = self._C_action.createVecRight()
                self._C_response = self._C_action.createVecLeft()
                self._correction = self._operator.createVecLeft()
            self._K = None
            self.F = None
            self.C = None
            self.H = None
            self.components = None
            self._K_released = True
            self._F_H_released = True
            self._F_C_H_references_released = self._C_action is None
            self._borrowed_component_handles_released = True

    def mark_borrowed_matrices_released(self) -> None:
        if not self._compact_storage:
            raise ValueError("Only compact storage has detached borrowed matrices")
        self._F_H_matrices_released = True
        self._F_C_H_matrices_released = self._C_action is None

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact Woodbury inverse without touching borrowed objects."""

        if self._destroyed:
            raise RuntimeError("Woodbury oracle has been destroyed")
        if (
            source.getSize() != self._source_size
            or target.getSize() != self._target_size
        ):
            raise ValueError("Woodbury source/target size does not match F")
        started = perf_counter()
        self.base_inverse.solve(source, self._z)
        self._apply_base_solve_count += 1
        self.D.mult(self._z, self._d_work)
        self._apply_d_count += 1
        d_values = _gather_owned_small_vector(self._d_work)
        try:
            q = lu_solve((self._lu, self._piv), d_values, check_finite=True)
        except ValueError as error:
            if "infs or NaNs" not in str(error):
                raise
            local_flags = 0
            if np.all(np.isfinite(self._z.getArray(readonly=True))):
                local_flags |= 1
            if np.all(np.isfinite(self._d_work.getArray(readonly=True))):
                local_flags |= 2
            if np.all(np.isfinite(d_values)):
                local_flags |= 4
            global_flags = int(self.comm.allreduce(local_flags, op=MPI.BAND))
            audit = {
                "stage": "woodbury_apply_lu_solve",
                "vector": "lu_solve_input",
                "finite": False,
                "base_inverse_solution_finite": bool(global_flags & 1),
                "modal_work_finite": bool(global_flags & 2),
                "gathered_modal_rhs_finite": bool(global_flags & 4),
                "error": str(error),
            }
            self._last_failure_audit = audit
            enriched = ValueError(
                "Woodbury finite audit failed at "
                f"stage={audit['stage']}, vector={audit['vector']}: {error}"
            )
            enriched.finite_audit = audit
            raise enriched from error
        self._z.copy(target)
        if self._streaming_w_batch_size is None:
            target.getArray()[:] += self._W_local @ q
        else:
            if (
                self._C_action is None
                or self._C_input is None
                or self._C_response is None
                or self._correction is None
            ):
                raise RuntimeError("Streaming-W C action is not available")
            _set_owned_small_vector(self._C_input, q)
            self._C_action.mult(self._C_input, self._C_response)
            self._apply_c_count += 1
            self.base_inverse.solve(self._C_response, self._correction)
            self._apply_base_solve_count += 1
            target.axpy(PETSc.ScalarType(1.0), self._correction)
        local_apply_finite = bool(
            np.all(np.isfinite(self._z.getArray(readonly=True)))
            and np.all(np.isfinite(self._d_work.getArray(readonly=True)))
            and np.all(np.isfinite(q))
            and np.all(np.isfinite(target.getArray(readonly=True)))
            and (
                self._correction is None
                or np.all(np.isfinite(self._correction.getArray(readonly=True)))
            )
        )
        self._arrays_finite = bool(
            self._arrays_finite and self.comm.allreduce(local_apply_finite, op=MPI.LAND)
        )
        self.apply_count += 1
        self._apply_seconds += _max_over_comm(
            self.comm,
            perf_counter() - started,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        W_local = self._W_local
        K = self._K
        lu = self._lu
        piv = self._piv
        k_shape = (
            self._K_shape
            if K is None and self._compact_storage
            else (None if K is None else list(K.shape))
        )
        k_dtype = (
            self._K_dtype
            if K is None and self._compact_storage
            else (None if K is None else str(K.dtype))
        )
        k_nbytes = (
            self._K_nbytes
            if K is None and self._compact_storage
            else (None if K is None else int(K.nbytes))
        )
        lu_shape = (
            self._lu_shape
            if lu is None and self._compact_storage
            else (None if lu is None else list(lu.shape))
        )
        lu_nbytes = (
            self._lu_nbytes
            if lu is None and self._compact_storage
            else (None if lu is None else int(lu.nbytes))
        )
        piv_shape = (
            self._piv_shape
            if piv is None and self._compact_storage
            else (None if piv is None else list(piv.shape))
        )
        piv_nbytes = (
            self._piv_nbytes
            if piv is None and self._compact_storage
            else (None if piv is None else int(piv.nbytes))
        )
        streaming = self._streaming_w_batch_size is not None
        return {
            "base_identity": self.base_identity,
            "n_aux": self.n_aux,
            "normal_equations": False,
            "W_local_shape": None if W_local is None else list(W_local.shape),
            "W_local_nbytes": None if W_local is None else int(W_local.nbytes),
            "W_resident": W_local is not None,
            "streaming_w_storage": streaming,
            "streaming_w_batch_size": self._streaming_w_batch_size,
            "streaming_w_batch_peak_bytes": int(self._streaming_w_batch_peak_bytes),
            "streaming_w_batch_local_peak_bytes": int(
                self._streaming_w_batch_local_peak_bytes
            ),
            "streaming_w_batch_peak_scope": (
                "max_rank_local_dense_response_buffer"
                if streaming
                else "not_applicable"
            ),
            "K_shape": k_shape,
            "K_dtype": k_dtype,
            "K_nbytes": k_nbytes,
            "K_rank": self._K_rank,
            "K_condition_number": self._K_condition,
            "arrays_finite": bool(self._arrays_finite),
            "last_failure_audit": self._last_failure_audit,
            "LU_shape": lu_shape,
            "LU_nbytes": (
                None
                if lu_nbytes is None or piv_nbytes is None
                else int(lu_nbytes + piv_nbytes)
            ),
            "LU_array_nbytes": lu_nbytes,
            "pivots_shape": piv_shape,
            "pivots_nbytes": piv_nbytes,
            "compact_storage": bool(self._compact_storage),
            "factor_only_storage": bool(self._factor_only_storage),
            "K_released": bool(self._K_released),
            "F_C_H_references_released": bool(self._F_C_H_references_released),
            "F_C_H_matrices_released": bool(self._F_C_H_matrices_released),
            "F_H_released": bool(self._F_H_released),
            "F_H_matrices_released": bool(self._F_H_matrices_released),
            "borrowed_component_handles_released": bool(
                self._borrowed_component_handles_released
            ),
            "D_retained": bool(self._D_retained),
            "setup_factor_solve_count": int(self._setup_factor_solve_count),
            "setup_d_apply_count": int(self._setup_d_apply_count),
            "setup_batch_count": (
                0
                if self._streaming_w_batch_size is None
                and self._setup_factor_solve_count == 0
                else (
                    1
                    if self._streaming_w_batch_size is None
                    else int(
                        (self.n_aux + self._streaming_w_batch_size - 1)
                        // self._streaming_w_batch_size
                    )
                )
            ),
            "apply_base_solve_count": int(self._apply_base_solve_count),
            "apply_base_solve_count_per_apply": (2 if streaming else 1),
            "apply_D_count": int(self._apply_d_count),
            "apply_C_count": int(self._apply_c_count),
            "C_action_owned": bool(self._C_action_owned),
            "C_action_resident": self._C_action is not None,
            "C_action_released": bool(self._C_action_owned and self._C_action is None),
            "setup_seconds": float(self._setup_seconds),
            "apply_count": int(self.apply_count),
            "apply_seconds": float(self._apply_seconds),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        """Release owned scratch and dense data; borrowed components survive."""

        if self._destroyed:
            return
        if self._z is not None:
            self._z.destroy()
        if self._d_work is not None:
            self._d_work.destroy()
        for vector_name in ("_C_input", "_C_response", "_correction"):
            vector = getattr(self, vector_name)
            if vector is not None:
                vector.destroy()
                setattr(self, vector_name, None)
        if self._C_action_owned and self._C_action is not None:
            self._C_action.destroy()
            self._C_action = None
            self._F_C_H_matrices_released = bool(self._F_H_matrices_released)
            self._F_C_H_references_released = True
            self._borrowed_component_handles_released = True
        self._z = None
        self._d_work = None
        self._W_local = None
        self._K = None
        self._lu = None
        self._piv = None
        self.D = None
        self.base_inverse = None
        self._operator = None
        self._D_retained = False
        self._destroyed = True


class ResearchExactFactorInverse:
    """Research-only PETSc LU factor that borrows, but never destroys, ``F``."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        *,
        factor_solver_type: str | None = "mumps",
        factor_only_storage: bool = False,
        compressed_factor_profile: str | None = None,
        lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        if not isinstance(matrix, PETSc.Mat):
            raise TypeError("Exact research factor requires a PETSc matrix")
        if str(matrix.getType()).lower() == "python":
            raise ValueError("Exact research factor requires an explicit F matrix")
        if matrix.getSize()[0] != matrix.getSize()[1]:
            raise ValueError("Exact research factor requires square F")
        self.matrix = matrix
        self.factor_solver_type = factor_solver_type
        self._factor_only_storage = bool(factor_only_storage)
        expected_mumps_controls = None
        if compressed_factor_profile is not None:
            expected_mumps_controls = mumps_blr_v5_h4_controls(
                compressed_factor_profile
            )
        if compressed_factor_profile is not None and not self._factor_only_storage:
            raise ValueError("Compressed factor storage requires factor-only storage")
        if compressed_factor_profile is not None and factor_solver_type != "mumps":
            raise ValueError("V5 h4 BLR profile requires factor_solver_type='mumps'")
        self.compressed_factor_profile = compressed_factor_profile
        self.factor_matrix: PETSc.Mat | None = None
        self._factor_matrix_stats: dict[str, Any] | None = None
        self._factor_matrix_owned = False
        self._ksp_destroyed = False
        self._lifecycle_callback = lifecycle_callback
        self._factor_inventory: dict[str, Any] | None = None
        self._mumps_controls_requested: dict[str, Any] | None = None
        self._mumps_controls_observed: dict[str, Any] | None = None
        self._mumps_controls_verified: bool | None = None
        self._mumps_infog: dict[str, int | None] = {"1": None, "2": None}
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.ksp.setOperators(matrix)
        self.ksp.setType("preonly")
        self.ksp.setErrorIfNotConverged(True)
        pc = self.ksp.getPC()
        pc.setType("lu")
        if factor_solver_type is not None:
            pc.setFactorSolverType(str(factor_solver_type))
        if lifecycle_callback is not None:
            lifecycle_callback(
                "factor_setup_begin",
                {
                    "factor_solver_type": factor_solver_type,
                    "matrix_stats": _petsc_matrix_stats(matrix, assemble=False),
                },
            )
        factor_inventory: dict[str, Any] | None = None
        try:
            configured_factor = _configure_v5_blr_factor(pc, compressed_factor_profile)
            if configured_factor is None and factor_solver_type == "mumps":
                pc.setFactorSetUpSolverType()
                configured_factor = pc.getFactorMatrix()
                configured_factor.setMumpsIcntl(
                    14, MUMPS_EXACT_WORKSPACE_RELAXATION_PERCENT
                )
                self._mumps_controls_requested = {
                    "icntl_14": MUMPS_EXACT_WORKSPACE_RELAXATION_PERCENT
                }
            elif configured_factor is not None:
                self._mumps_controls_requested = expected_mumps_controls
            self.ksp.setUp()
            if configured_factor is not None:
                if compressed_factor_profile is None:
                    self._mumps_controls_observed = {
                        "icntl_14": configured_factor.getMumpsIcntl(14)
                    }
                else:
                    self._mumps_controls_observed = {
                        "icntl_35": configured_factor.getMumpsIcntl(35),
                        "cntl_7": configured_factor.getMumpsCntl(7),
                        "icntl_14": configured_factor.getMumpsIcntl(14),
                    }
                self._mumps_controls_verified = bool(
                    self._mumps_controls_observed == self._mumps_controls_requested
                )
                if not self._mumps_controls_verified:
                    raise RuntimeError(
                        "MUMPS workspace controls were not read back exactly"
                    )
            factor_inventory = _petsc_factor_inventory(self.ksp)
            self._factor_inventory = factor_inventory
            if factor_solver_type == "mumps" and factor_inventory.get(
                "mumps_api_available"
            ):
                raw_infog = factor_inventory["mumps_raw_infog"]
                self._mumps_infog = {
                    "1": raw_infog.get("1"),
                    "2": raw_infog.get("2"),
                }
                if self._mumps_infog["1"] is not None and self._mumps_infog["1"] < 0:
                    raise RuntimeError(
                        "MUMPS exact factorization failed: "
                        f"INFOG(1)={self._mumps_infog['1']}, "
                        f"INFOG(2)={self._mumps_infog['2']}"
                    )
        except Exception:
            self.ksp.destroy()
            self.ksp = None
            raise
        self._destroyed = False
        self._solve_count = 0
        if self._factor_only_storage:
            self.factor_matrix = pc.getFactorMatrix()
            self.factor_matrix.incRef()
            self._factor_matrix_owned = True
            self._factor_matrix_stats = _petsc_matrix_stats(
                self.factor_matrix, assemble=False
            )
            self.ksp.destroy()
            self.ksp = None
            self._ksp_destroyed = True
        if lifecycle_callback is not None:
            lifecycle_callback(
                "factor_ready",
                {
                    "factor_solver_type": factor_solver_type,
                    "factor_inventory": factor_inventory,
                    "factor_only_storage": self._factor_only_storage,
                    "compressed_factor_profile": compressed_factor_profile,
                    "mumps_controls_requested": self._mumps_controls_requested,
                    "mumps_controls_observed": self._mumps_controls_observed,
                    "mumps_controls_verified": self._mumps_controls_verified,
                    "ksp_destroyed": self._ksp_destroyed,
                    "factor_matrix_owned": self._factor_matrix_owned,
                },
            )

    @property
    def factor_only_storage(self) -> bool:
        return self._factor_only_storage

    @property
    def operator(self) -> PETSc.Mat | None:
        return self.factor_matrix if self._factor_only_storage else self.matrix

    def release_borrowed_matrix(self) -> None:
        if not self._factor_only_storage:
            raise ValueError("Only factor-only storage can release its borrowed matrix")
        self.matrix = None

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Exact research factor has been destroyed")
        operator = self.operator
        if operator is None:
            raise RuntimeError("Exact research factor has no solve operator")
        if source.getSize() != operator.getSize()[1]:
            raise ValueError("Exact research factor source has the wrong size")
        if target.getSize() != operator.getSize()[0]:
            raise ValueError("Exact research factor target has the wrong size")
        target.set(0.0)
        if self._factor_only_storage:
            self.factor_matrix.solve(source, target)
        else:
            self.ksp.solve(source, target)
            reason = int(self.ksp.getConvergedReason())
            if reason < 0:
                raise RuntimeError(
                    f"Exact research LU solve failed with reason {reason}"
                )
        self._solve_count += 1

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.solve(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        compressed = self.compressed_factor_profile is not None
        direct_factor_count = 0 if self._destroyed else 1
        exact_factor_count = 0 if self._destroyed or compressed else 1
        compressed_factor_count = 0 if self._destroyed else int(compressed)
        diagnostics = {
            "research_only": True,
            "operator_identity": (
                "research_mumps_blr_compressed_side_factor"
                if compressed
                else "research_exact_side_lu"
            ),
            "factor_solver_type": self.factor_solver_type,
            "ksp_created": True,
            "ksp_destroyed": bool(self._ksp_destroyed),
            "factor_only_storage": bool(self._factor_only_storage),
            "factor_matrix_owned": bool(self._factor_matrix_owned),
            "factor_matrix_alive": self.factor_matrix is not None,
            "factor_matrix_stats": self._factor_matrix_stats,
            "borrowed_matrix_released": self.matrix is None,
            "direct_factor_count": direct_factor_count,
            "direct_factor_count_owned": direct_factor_count,
            "exact_factor_count": exact_factor_count,
            "compressed_factor_count": compressed_factor_count,
            "global_hybrid_direct_factor_count": 0,
            "solve_count": int(self._solve_count),
            "factor_destroyed": bool(self._destroyed),
        }

        if not compressed and self.factor_solver_type == "mumps":
            diagnostics.update(
                {
                    "factor_inventory": self._factor_inventory,
                    "mumps_icntl_14_requested_percent": (
                        MUMPS_EXACT_WORKSPACE_RELAXATION_PERCENT
                    ),
                    "mumps_icntl_14_observed_percent": (
                        None
                        if self._mumps_controls_observed is None
                        else self._mumps_controls_observed.get("icntl_14")
                    ),
                    "mumps_workspace_relaxation_verified": bool(
                        self._mumps_controls_verified
                    ),
                    "mumps_infog_1": self._mumps_infog["1"],
                    "mumps_infog_2": self._mumps_infog["2"],
                }
            )

        if compressed:
            return {
                **diagnostics,
                "compressed_factor_profile": self.compressed_factor_profile,
                "mumps_controls_requested": mumps_blr_v5_h4_controls(
                    self.compressed_factor_profile
                ),
                "mumps_controls_observed": self._mumps_controls_observed,
                "mumps_controls_verified": self._mumps_controls_verified,
                "true_residual_authority": "external_full_explicit_side_residual",
            }
        return diagnostics

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._factor_only_storage:
            if self.factor_matrix is not None:
                self.factor_matrix.destroy()
                self.factor_matrix = None
        else:
            self.ksp.destroy()
            self.ksp = None
        self.matrix = None if self._factor_only_storage else self.matrix
        self._destroyed = True


class ResearchExactSideLuAction:
    """Default exact-side LU plus an optional frozen BLR candidate profile."""

    def __init__(
        self,
        explicit_f: PETSc.Mat,
        components: Any,
        *,
        factor_solver_type: str | None = "mumps",
        qualification_scope: str | None = None,
        explicit_opt_in: bool = False,
        factor_only_storage: bool = False,
        compressed_factor_profile: str | None = None,
        streaming_w_batch_size: int | None = None,
        lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> None:
        if getattr(components, "F", None) is not explicit_f:
            raise ValueError("Research exact-side action must use components.F itself")
        if streaming_w_batch_size is not None and not explicit_opt_in:
            raise ValueError("Streaming-W storage requires explicit opt-in")
        if compressed_factor_profile is not None and not explicit_opt_in:
            raise ValueError("Compressed factor storage requires explicit opt-in")
        self.factor = ResearchExactFactorInverse(
            explicit_f,
            factor_solver_type=factor_solver_type,
            factor_only_storage=factor_only_storage,
            compressed_factor_profile=compressed_factor_profile,
            lifecycle_callback=lifecycle_callback,
        )
        try:
            self.woodbury = HybridLocalDtnWoodburyOracle(
                self.factor,
                components,
                base_identity=(
                    "research_mumps_blr_compressed_side_factor"
                    if compressed_factor_profile is not None
                    else "research_exact_F_direct"
                ),
                compact_storage=factor_only_storage,
                streaming_w_batch_size=streaming_w_batch_size,
            )
        except Exception:
            self.factor.destroy()
            raise
        if factor_only_storage:
            self.factor.release_borrowed_matrix()
            self.operator = self.factor.operator
            self.components = None
        else:
            self.operator = components.F
            self.components = components
        self.qualification_scope = qualification_scope
        self.explicit_opt_in = bool(explicit_opt_in)
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Research exact-side action has been destroyed")
        self.woodbury.apply(source, target)

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        factor = self.factor.diagnostics
        woodbury = self.woodbury.diagnostics
        diagnostics = {
            "research_only": not self.explicit_opt_in,
            "operator_identity": (
                "research_mumps_blr_compressed_side_lu_woodbury"
                if self.factor.compressed_factor_profile is not None
                else "research_exact_side_lu_woodbury"
            ),
            "factor_solver_type": factor["factor_solver_type"],
            "ksp_created": True,
            "ksp_destroyed": factor["ksp_destroyed"],
            "factor_only_storage": factor["factor_only_storage"],
            "factor_matrix_owned": factor["factor_matrix_owned"],
            "direct_factor_count": factor["direct_factor_count"],
            "direct_factor_count_owned": factor["direct_factor_count_owned"],
            "ilu_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
            "woodbury": woodbury,
            "apply_count": int(woodbury["apply_count"]),
            "destroyed": bool(self._destroyed),
        }
        if self.factor.compressed_factor_profile is not None:
            diagnostics.update(
                {
                    "compressed_factor_profile": self.factor.compressed_factor_profile,
                    "exact_factor_count": factor["exact_factor_count"],
                    "compressed_factor_count": factor["compressed_factor_count"],
                    "direct_factor_count": factor["direct_factor_count"],
                    "direct_factor_count_owned": factor["direct_factor_count_owned"],
                    "global_direct_factor_count": 0,
                    "mumps_controls_requested": factor["mumps_controls_requested"],
                    "mumps_controls_observed": factor["mumps_controls_observed"],
                    "mumps_controls_verified": factor["mumps_controls_verified"],
                    "general_production": False,
                    "true_residual_authority": "external_full_explicit_side_residual",
                }
            )
        if self.explicit_opt_in:
            diagnostics.update(
                {
                    "qualification_scope": self.qualification_scope,
                    "explicit_opt_in": True,
                    "case_qualification_opt_in": True,
                    "general_production": False,
                    "ordinary_default": False,
                    "ordinary_default_changed": False,
                    "nested_iterative_ksp_count": 0,
                    "local_direct_preonly_ksp_count": 1,
                    "local_direct_solve_count": int(factor["solve_count"]),
                    "local_ksp_role": "preonly_lu_direct_factor",
                }
            )
        if self.factor.compressed_factor_profile is not None:
            diagnostics.update(
                {
                    "research_only": True,
                    "component_candidate": True,
                    "general_production": False,
                    "case_qualification_opt_in": False,
                }
            )
        return diagnostics

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.woodbury.destroy()
        self.factor.destroy()
        if self.factor.factor_only_storage:
            self.operator = None
            self.components = None
        self._destroyed = True


def create_research_exact_side_lu_action(
    explicit_f: PETSc.Mat,
    components: Any,
    *,
    factor_solver_type: str | None = "mumps",
    qualification_scope: str | None = None,
    explicit_opt_in: bool = False,
    factor_only_storage: bool = False,
    compressed_factor_profile: str | None = None,
    streaming_w_batch_size: int | None = None,
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> ResearchExactSideLuAction:
    """Create the historical research action or an explicit case qualification.

    Without a qualification scope the action retains its research-only
    diagnostics and behavior.
    """

    if getattr(components, "F", None) is not explicit_f:
        raise ValueError("Research exact-side factor must use components.F itself")
    return ResearchExactSideLuAction(
        explicit_f,
        components,
        factor_solver_type=factor_solver_type,
        qualification_scope=qualification_scope,
        explicit_opt_in=explicit_opt_in,
        factor_only_storage=factor_only_storage,
        compressed_factor_profile=compressed_factor_profile,
        streaming_w_batch_size=streaming_w_batch_size,
        lifecycle_callback=lifecycle_callback,
    )


class _FixedBaseApplyAdapter:
    """Adapt one borrowed fixed smoother callback to the Oracle solve contract."""

    def __init__(self, base_action: Any) -> None:
        if not hasattr(base_action, "apply"):
            raise TypeError(
                "Fixed Woodbury base action must expose apply(source, target)"
            )
        self.base_action = base_action

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.base_action.apply(source, target)


class HybridLocalDtnWoodburyFixedAction:
    """Non-owning one-apply adapter around the fixed Woodbury action."""

    operator_identity = "whole_endcap_ilu0_woodbury_fixed_action"

    def __init__(
        self,
        base_action: Any,
        components: Any,
        *,
        base_identity: str = "whole_endcap_ilu0_fixed_smoother",
        operator_identity: str | None = None,
        ilu_levels: int | None = None,
        residual_operator: PETSc.Mat | None = None,
        residual_correction_steps: int = 1,
    ) -> None:
        if residual_correction_steps not in (1, 2, 4, 8):
            raise ValueError("Residual correction steps must be one of 1, 2, 4, or 8")
        if residual_correction_steps > 1 and residual_operator is None:
            raise ValueError(
                "Multi-pass correction requires a borrowed residual operator"
            )
        if residual_correction_steps == 1 and residual_operator is not None:
            raise ValueError(
                "A residual operator is only valid for two-pass correction"
            )
        self.base_action = base_action
        self.components = components
        self.operator = components.F
        if ilu_levels is not None and int(ilu_levels) not in {0, 1}:
            raise ValueError("Fixed Woodbury action supports ILU(0) or ILU(1)")
        self.ilu_levels = None if ilu_levels is None else int(ilu_levels)
        self._base_operator_identity = operator_identity or self.operator_identity
        self.operator_identity = (
            f"{self._base_operator_identity}_two_pass_residual_correction"
            if residual_correction_steps == 2
            else (
                f"{self._base_operator_identity}_{residual_correction_steps}_pass_residual_correction"
                if residual_correction_steps > 2
                else self._base_operator_identity
            )
        )
        self.residual_operator = residual_operator
        self._residual_operator_borrowed = residual_operator is not None
        self.residual_correction_steps = int(residual_correction_steps)
        self._logical_apply_count = 0
        self._residual: PETSc.Vec | None = None
        self._correction: PETSc.Vec | None = None
        self._correction_operator_matrix_free = bool(
            residual_operator is not None
            and str(residual_operator.getType()).lower() == "python"
        )
        base_diagnostics = getattr(base_action, "diagnostics", None)
        if callable(base_diagnostics):
            base_diagnostics = base_diagnostics()
        if not isinstance(base_diagnostics, dict):
            raise TypeError("Fixed Woodbury base action needs diagnostics")
        if (
            "factor_count" not in base_diagnostics
            or "ksp_created" not in base_diagnostics
        ):
            raise ValueError(
                "Fixed Woodbury base diagnostics need factor_count and ksp_created"
            )
        self._base_qualification = {
            "factor_count": int(base_diagnostics["factor_count"]),
            "ksp_created": bool(base_diagnostics["ksp_created"]),
        }
        self._base_adapter = _FixedBaseApplyAdapter(base_action)
        self.woodbury = HybridLocalDtnWoodburyOracle(
            self._base_adapter,
            components,
            base_identity=base_identity,
        )
        if self.residual_correction_steps > 1:
            self._residual = self.operator.createVecLeft()
            self._correction = self.operator.createVecLeft()
        self._destroyed = False
        self._pre_destroy_diagnostics: dict[str, Any] | None = None
        self._base_pre_destroy_diagnostics: dict[str, Any] | None = None

    def _base_diagnostics_now(self) -> dict[str, Any]:
        diagnostics = getattr(self.base_action, "diagnostics", None)
        if callable(diagnostics):
            diagnostics = diagnostics()
        if not isinstance(diagnostics, dict):
            raise RuntimeError("Fixed Woodbury base diagnostics are unavailable")
        return dict(diagnostics)

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Fixed Woodbury action has been destroyed")
        self.woodbury.apply(source, target)
        for _ in range(self.residual_correction_steps - 1):
            self.residual_operator.mult(target, self._residual)
            self._residual.scale(PETSc.ScalarType(-1.0))
            self._residual.axpy(PETSc.ScalarType(1.0), source)
            self.woodbury.apply(self._residual, self._correction)
            target.axpy(PETSc.ScalarType(1.0), self._correction)
        self._logical_apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        woodbury = (
            self._pre_destroy_diagnostics
            if self._pre_destroy_diagnostics is not None
            else self.woodbury.diagnostics
        )
        base_diagnostics = (
            self._base_pre_destroy_diagnostics
            if self._base_pre_destroy_diagnostics is not None
            else self._base_diagnostics_now()
        )
        diagnostics = {
            "operator_identity": self.operator_identity,
            "residual_correction_steps": int(self.residual_correction_steps),
            "residual_correction_operator_borrowed": self._residual_operator_borrowed,
            "correction_operator_matrix_free": self._correction_operator_matrix_free,
            "logical_apply_count": int(self._logical_apply_count),
            "base_identity": woodbury["base_identity"],
            "base_factor_count": int(self._base_qualification["factor_count"]),
            "base_factor_borrowed": True,
            "local_direct_factor_count": 0,
            "local_direct_factor_count_owned": 0,
            "global_hybrid_direct_factor_count": 0,
            "nested_ksp_created": bool(self._base_qualification["ksp_created"]),
            "nested_ksp_count": int(self._base_qualification["ksp_created"]),
            "exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "base_diagnostics": base_diagnostics,
            "apply_count": int(self._logical_apply_count),
            "raw_apply_count": int(woodbury["apply_count"]),
            "woodbury": dict(woodbury),
            "components_borrowed": True,
            "owned_action_data_released": bool(self._destroyed),
            "destroyed": bool(self._destroyed),
        }
        if self.ilu_levels is not None:
            diagnostics["ilu_levels"] = int(self.ilu_levels)
        return diagnostics

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._base_pre_destroy_diagnostics = self._base_diagnostics_now()
        self._pre_destroy_diagnostics = dict(self.woodbury.diagnostics)
        self.woodbury.destroy()
        if self._residual is not None:
            self._residual.destroy()
            self._residual = None
        if self._correction is not None:
            self._correction.destroy()
            self._correction = None
        self.residual_operator = None
        self._destroyed = True


class _FixedBudgetPythonPcContext:
    """Borrow one fixed side action as a PETSc Python right-preconditioner."""

    def __init__(self, action: Any) -> None:
        self.action: Any | None = action

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.action is None:
            raise RuntimeError("fixed-budget Python PC has been destroyed")
        self.action.apply(source, target)

    def destroy(self, _pc: PETSc.PC) -> None:
        self.action = None


class HybridLocalDtnWoodburyFixedBudgetKrylovAction:
    """Apply a fixed-budget side Krylov inverse with a borrowed one-pass PC.

    This research-only action owns only its inner KSP and Python-PC context.
    The side operator and the fixed Woodbury action are borrowed.  The returned
    vector is intentionally judged by an external true residual; this class
    records the KSP outcome but does not turn it into a convergence claim.
    """

    _ALLOWED_BUDGETS = (8, 16, 32)
    operator_identity = "fixed_budget_side_fgmres_right_fixed_woodbury"

    def __init__(
        self,
        operator: PETSc.Mat,
        right_preconditioner: Any,
        *,
        budget: int,
    ) -> None:
        if budget not in self._ALLOWED_BUDGETS:
            raise ValueError("Fixed-budget side Krylov budget must be 8, 16, or 32")
        if (
            not isinstance(operator, PETSc.Mat)
            or str(operator.getType()).lower() != "python"
        ):
            raise TypeError(
                "Fixed-budget side Krylov requires a matrix-free MatPython operator"
            )
        if not isinstance(right_preconditioner, HybridLocalDtnWoodburyFixedAction):
            raise TypeError(
                "Fixed-budget side Krylov requires HybridLocalDtnWoodburyFixedAction"
            )
        right_diagnostics = right_preconditioner.diagnostics
        if (
            right_diagnostics.get("residual_correction_steps") != 1
            or right_diagnostics.get("local_direct_factor_count") != 0
            or right_diagnostics.get("global_hybrid_direct_factor_count") != 0
        ):
            raise ValueError(
                "Fixed-budget side Krylov requires one-pass factor-free right PC"
            )

        self.operator = operator
        self.right_preconditioner = right_preconditioner
        self.budget = int(budget)
        self._right_diagnostics = dict(right_diagnostics)
        self._direct_factor_count = int(right_diagnostics["local_direct_factor_count"])
        self._global_direct_factor_count = int(
            right_diagnostics["global_hybrid_direct_factor_count"]
        )
        self._comm = operator.getComm().tompi4py()
        self._right_preconditioner_identity = str(
            self._right_diagnostics.get(
                "operator_identity", type(right_preconditioner).__name__
            )
        )
        self._pc_context = _FixedBudgetPythonPcContext(right_preconditioner)
        self._inner_ksp = PETSc.KSP().create(operator.getComm())
        self._inner_ksp.setOperators(operator)
        self._inner_ksp.setType("fgmres")
        self._inner_ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self._inner_ksp.setGMRESRestart(self.budget)
        self._inner_ksp.setNormType(PETSc.KSP.NormType.NONE)
        self._inner_ksp.setInitialGuessNonzero(False)
        self._inner_ksp.setTolerances(max_it=self.budget)
        pc = self._inner_ksp.getPC()
        pc.setType("python")
        pc.setPythonContext(self._pc_context)
        self._inner_ksp.setUp()
        self._apply_count = 0
        self._total_iterations = 0
        self._last_iterations: int | None = None
        self._last_reason: int | None = None
        self._last_reason_label: str | None = None
        self._last_zero_rhs_exact = False
        self._last_seconds: float | None = None
        self._total_seconds = 0.0
        self._inner_ksp_destroyed = False
        self._pc_context_destroyed = False
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Fixed-budget side Krylov action has been destroyed")
        if source.getSize() != self.operator.getSize()[1]:
            raise ValueError("Fixed-budget side Krylov source has the wrong size")
        if target.getSize() != self.operator.getSize()[0]:
            raise ValueError("Fixed-budget side Krylov target has the wrong size")
        target.set(0.0)
        source_norm = float(source.norm())
        if not np.isfinite(source_norm):
            error = ValueError("Fixed-budget side Krylov source norm is non-finite")
            error.finite_audit = {
                "stage": "fixed_budget_apply_input",
                "vector": "source",
                "finite": False,
                "source_norm": source_norm,
            }
            raise error
        exact_zero = source_norm == 0.0
        started = perf_counter()
        if exact_zero:
            elapsed = _max_over_comm(self._comm, perf_counter() - started)
            self._apply_count += 1
            self._last_iterations = 0
            self._last_reason = None
            self._last_reason_label = "zero_rhs_exact"
            self._last_zero_rhs_exact = True
            self._last_seconds = float(elapsed)
            self._total_seconds += float(elapsed)
            return
        self._inner_ksp.solve(source, target)
        elapsed = _max_over_comm(self._comm, perf_counter() - started)
        iterations = int(self._inner_ksp.getIterationNumber())
        reason = int(self._inner_ksp.getConvergedReason())
        self._apply_count += 1
        self._total_iterations += iterations
        self._last_iterations = iterations
        self._last_reason = reason
        self._last_reason_label = "petsc_ksp"
        self._last_zero_rhs_exact = False
        self._last_seconds = float(elapsed)
        self._total_seconds += float(elapsed)

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "research_only": True,
            "operator_identity": self.operator_identity,
            "requested_budget": int(self.budget),
            "ksp_type": "fgmres",
            "pc_side": "right",
            "restart": int(self.budget),
            "norm_type": "none",
            "zero_initial_guess": True,
            "right_preconditioner_identity": self._right_preconditioner_identity,
            "right_preconditioner_borrowed": True,
            "direct_factor_count": self._direct_factor_count,
            "global_hybrid_direct_factor_count": self._global_direct_factor_count,
            "apply_count": int(self._apply_count),
            "total_inner_iterations": int(self._total_iterations),
            "last_inner_iterations": self._last_iterations,
            "last_converged_reason": self._last_reason,
            "last_converged_reason_label": self._last_reason_label,
            "zero_rhs_exact": bool(self._last_zero_rhs_exact),
            "last_apply_seconds": self._last_seconds,
            "total_apply_seconds": float(self._total_seconds),
            "inner_ksp_created": True,
            "inner_ksp_destroyed": bool(self._inner_ksp_destroyed),
            "pc_context_destroyed": bool(self._pc_context_destroyed),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._inner_ksp.destroy()
        self._inner_ksp = None
        self._inner_ksp_destroyed = True
        self._pc_context = None
        self._pc_context_destroyed = True
        self.right_preconditioner = None
        self.operator = None
        self._destroyed = True
