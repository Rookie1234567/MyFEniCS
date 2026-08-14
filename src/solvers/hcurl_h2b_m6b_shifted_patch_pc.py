"""M6B shifted full-space PC and PETSc adapters.

The allowed ``beta=0.5`` and ``beta=1`` patch operators are non-Hermitian.
The PC therefore uses the ordinary complex inner product to choose one
residual-minimizing scalar after an additive row-complete LU correction.  It
performs one matrix-free
shifted action per apply and retains no cell solution or assembled matrix.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from petsc4py import PETSc

from .hcurl_h2b_m6b_shifted_lu_store import (
    H2BM6BShiftedLUPatchStore,
    M6B_ALLOWED_SHIFTED_BETAS,
    M6B_SHIFTED_LU_STORE_SCHEMA,
)
from .hcurl_m6b_sparse_range import SparseM6BRangeCarrier

__all__ = (
    "M6B_SHIFTED_PC_SCHEMA",
    "M6B_FIXED_SCREEN_ITERATIONS",
    "M6B_FIXED_RESTART",
    "M6B_FIXED_MAX_IT",
    "M6B_W4_SCHEMA",
    "M6B_W4_KSP_ITERATIONS",
    "M6B_W4_PC_APPLY_BUDGETS",
    "M6B_W5_SCHEMA",
    "M6B_ONLINE_RSS_LIMIT_BYTES",
    "M6B_POU_CLOSURE_LIMIT",
    "M6B_SCREEN_RHO_LIMITS",
    "M6B_IMPROVEMENT_LIMIT",
    "M6B_SHARED_VOLUME_OPERATOR",
    "M6B_SHARED_VOLUME_REPRESENTATION",
    "M6B_W2R_RANGE_PC_SCHEMA",
    "m6b_shifted_local_matrix",
    "m6b_material_tag_coverage",
    "H2BM6BShiftedPatchPC",
    "H2BM6BShiftedRangePC",
    "H2BM6BProjectedRangePC",
    "M6BShiftedPCContext",
    "M6BOuterMatPythonContext",
    "M6BNumpyOuterActionBridge",
    "M6BScreenCheckpointWriter",
    "build_m6b_volume_form",
    "build_m6b_outer_mat",
    "compose_m6b_physical_rhs",
    "recover_m6b_auxiliary",
    "evaluate_m6b_screen_gate",
    "evaluate_m6b_numeric_screen_gate",
    "run_m6b_right_fgmres_screen",
    "run_m6b_disk_backed_right_fgmres_screen",
    "run_m6b_right_fbcgs_screen",
)


M6B_SHIFTED_PC_SCHEMA = "task037.extra.h2b.m6b.shifted-patch-pc.v1"
M6B_W2_RANGE_PC_SCHEMA = "task037.extra.h2b.m6b.shifted-range-pc.v1"
M6B_W2R_RANGE_PC_SCHEMA = "task037.extra.h2b.m6b.projected-range-pc.v1"
M6B_FIXED_SCREEN_ITERATIONS = (20, 100, 150, 200)
M6B_FIXED_RESTART = 20
M6B_FIXED_MAX_IT = 200
M6B_W4_SCHEMA = "task037.extra.h2b.m6b.fbcgs-screen.v1"
M6B_W4_KSP_ITERATIONS = (10, 50, 75, 100)
M6B_W4_PC_APPLY_BUDGETS = (20, 100, 150, 200)
M6B_W5_SCHEMA = "task037.extra.h2b.m6b.disk-fgmres-screen.v1"
M6B_W4_KSP_TO_PC_BUDGET = dict(
    zip(M6B_W4_KSP_ITERATIONS, M6B_W4_PC_APPLY_BUDGETS)
)
M6B_ONLINE_RSS_LIMIT_BYTES = 1_900_000_000
M6B_POU_CLOSURE_LIMIT = 1.0e-14
M6B_SCREEN_RHO_LIMITS = {
    "iteration20": 0.60,
    "iteration100": 0.20,
    "iteration200": 0.08,
}
M6B_IMPROVEMENT_LIMIT = 0.15
M6B_SHARED_VOLUME_OPERATOR = (
    "C-k0^2*M_epsilon+i*beta*k0^2*M_abs_epsilon"
)
M6B_SHARED_VOLUME_REPRESENTATION = "exact_DG0_single_integral"
_COMPLEX128_BYTES = np.dtype(np.complex128).itemsize


def m6b_shifted_local_matrix(
    curl_tensor: np.ndarray,
    mass_tensor: np.ndarray,
    epsilon: complex,
    k0: float,
    beta: float,
) -> np.ndarray:
    """Form the fixed non-Hermitian local ``B_beta`` class matrix."""

    beta_value = float(beta)
    if beta_value not in M6B_ALLOWED_SHIFTED_BETAS:
        raise ValueError("M6B shifted local beta must be exactly 0.5 or 1")
    return np.asarray(
        curl_tensor
        + float(k0) ** 2
        * (-complex(epsilon) + 1j * beta_value * abs(complex(epsilon)))
        * mass_tensor,
        dtype=np.complex128,
        order="C",
    )


def m6b_material_tag_coverage(mesh_data: Any, cfg: Any) -> dict[str, Any]:
    """Validate and summarize the fixed air/substrate/grating cell tags."""

    mesh = mesh_data.mesh
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    indices = np.asarray(mesh_data.cell_tags.indices, dtype=np.int64)
    values = np.asarray(mesh_data.cell_tags.values, dtype=np.int64)
    if indices.ndim != 1 or values.ndim != 1 or indices.size != values.size:
        raise ValueError("M6B material cell tags have an invalid layout")
    owned = (indices >= 0) & (indices < owned_cells)
    owned_indices = indices[owned]
    owned_values = values[owned]
    if (
        owned_cells <= 0
        or owned_indices.size != owned_cells
        or np.unique(owned_indices).size != owned_cells
        or not np.array_equal(np.sort(owned_indices), np.arange(owned_cells))
    ):
        raise ValueError("M6B material cell tags do not cover each owned cell exactly once")
    tag_values = {
        "air": int(cfg.tags.air),
        "substrate": int(cfg.tags.substrate),
        "grating": int(cfg.tags.grating),
    }
    allowed = set(tag_values.values())
    observed = {int(value) for value in np.unique(owned_values)}
    if not observed or not observed.issubset(allowed):
        raise ValueError("M6B material cell tags are outside air/substrate/grating")
    return {
        "owned_cell_count": owned_cells,
        "allowed_tag_values": tag_values,
        "tag_counts": {
            name: int(np.count_nonzero(owned_values == value))
            for name, value in tag_values.items()
        },
        "complete": True,
    }


def build_m6b_volume_form(
    function_space: Any,
    mesh_data: Any,
    cfg: Any,
    *,
    beta: float = 1.0,
) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    """Build the fixed DG0 single-integral physical/shifted volume form.

    ``beta`` is a runtime scalar coefficient so beta zero and one have the
    same UFL/FFCx structure and module identity.  The two DG0 coefficients and
    the Constant are returned so callers keep them alive for the compiled
    action.  The fixed target has no PML or divergence term; those cases are
    intentionally rejected rather than represented by a different kernel.
    """

    beta_value = float(beta)
    if beta_value != 0.0 and beta_value not in M6B_ALLOWED_SHIFTED_BETAS:
        raise ValueError("M6B volume form beta is fixed to exactly 0, 0.5 or 1")
    if bool(cfg.use_pml) or float(cfg.pml_top_thickness) != 0.0 or float(
        cfg.pml_bottom_thickness
    ) != 0.0 or float(cfg.divergence_penalty) != 0.0:
        raise ValueError(
            "M6B shared volume form requires fixed no-PML zero-divergence physics"
        )
    import ufl
    from dolfinx import fem
    from petsc4py import PETSc

    from src.common.materials import relative_permittivity

    tag_coverage = m6b_material_tag_coverage(mesh_data, cfg)
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_data.mesh)
    epsilon = relative_permittivity(mesh_data, cfg)
    abs_epsilon = fem.Function(epsilon.function_space)
    abs_epsilon.x.array[:] = np.abs(epsilon.x.array)
    abs_epsilon.x.scatter_forward()
    beta_constant = fem.Constant(mesh_data.mesh, PETSc.ScalarType(beta_value))
    mass = ufl.inner(u, v)
    volume = (
        PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(ufl.curl(u), ufl.curl(v))
        - PETSc.ScalarType(float(cfg.k0) ** 2) * epsilon * mass
        + PETSc.ScalarType(1j * float(cfg.k0) ** 2)
        * beta_constant
        * abs_epsilon
        * mass
    ) * dx
    return volume, epsilon, abs_epsilon, beta_constant, tag_coverage


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _finite_vector(value: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.dtype != np.dtype(np.complex128)
        or array.ndim != 1
        or array.size != size
        or not array.flags.c_contiguous
        or not np.all(np.isfinite(array))
    ):
        raise ValueError(f"M6B {name} must be a finite complex128 vector")
    return array


def _false_materialization(value: Mapping[str, Any]) -> bool:
    required = (
        "global_matrix",
        "global_constraint_matrix",
        "patch_matrices",
        "per_cell_factor",
        "static_condensation",
        "trace_slab",
        "schur",
        "slab_factor",
    )
    return isinstance(value, Mapping) and all(value.get(key) is False for key in required)


class H2BM6BShiftedPatchPC:
    """Additive full-space LU patch PC with one exact shifted action."""

    def __init__(
        self,
        factor_store: H2BM6BShiftedLUPatchStore,
        *,
        global_row_count: int,
        shifted_action: Callable[[np.ndarray], np.ndarray],
        slave_identity_rows: Sequence[int] = (),
        task037_extra_m6b: bool = False,
    ) -> None:
        if task037_extra_m6b is not True:
            raise ValueError("M6B shifted PC requires explicit research opt-in")
        if not isinstance(factor_store, H2BM6BShiftedLUPatchStore):
            raise TypeError("M6B shifted PC requires the shifted LU store")
        if type(global_row_count) is not int or global_row_count <= 0:
            raise ValueError("M6B global row count is invalid")
        if not callable(shifted_action):
            raise TypeError("M6B shifted action must be callable")
        store_audit = factor_store.audit
        store_beta = store_audit.get("beta")
        if (
            store_audit.get("schema") != M6B_SHIFTED_LU_STORE_SCHEMA
            or store_beta not in M6B_ALLOWED_SHIFTED_BETAS
            or store_audit.get("full_dense_patch_matrix_retained") is not False
            or store_audit.get("factor_copy_count") != 0
            or store_audit.get("retained_total_gate") is not True
            or not _false_materialization(store_audit.get("materialization_identity", {}))
        ):
            raise ValueError("M6B shifted PC requires a closed LU store")
        self._store = factor_store
        self._beta = float(store_beta)
        self._global_row_count = global_row_count
        self._shifted_action = shifted_action
        self._cell_count = int(factor_store.cell_neighborhood_ids.size)
        if self._cell_count <= 0:
            raise ValueError("M6B shifted store has no cell references")
        cell_rows: list[np.ndarray] = []
        for cell_id in range(self._cell_count):
            rows = np.asarray(factor_store.cell_rows(cell_id))
            factor = factor_store.factor_for_cell(cell_id)
            if (
                rows.dtype != np.dtype(np.int64)
                or rows.ndim != 1
                or rows.size != int(factor.n)
                or rows.size == 0
                or np.any(rows < 0)
                or np.any(rows >= global_row_count)
                or np.unique(rows).size != rows.size
            ):
                raise ValueError("M6B cell row mapping is invalid")
            rows.setflags(write=False)
            cell_rows.append(rows)
        self._cell_rows = tuple(cell_rows)
        factor_cells: list[list[int]] = [
            [] for _ in range(int(store_audit["factor_count"]))
        ]
        for cell_id in range(self._cell_count):
            neighborhood_id = int(factor_store.cell_neighborhood_ids[cell_id])
            factor_id = int(
                factor_store.neighborhoods[neighborhood_id]["factor_id"]
            )
            if not 0 <= factor_id < len(factor_cells):
                raise ValueError("M6B factor mapping is invalid")
            factor_cells[factor_id].append(cell_id)
        if any(not cell_ids for cell_ids in factor_cells):
            raise ValueError("M6B every retained factor needs cell reuse")
        self._factor_cell_groups = tuple(tuple(cell_ids) for cell_ids in factor_cells)
        self._max_factor_multiplicity = max(
            len(cell_ids) for cell_ids in self._factor_cell_groups
        )
        covered = np.unique(np.concatenate(self._cell_rows))
        slaves = np.asarray(slave_identity_rows, dtype=np.int64)
        if slaves.ndim != 1 or np.unique(slaves).size != slaves.size:
            raise ValueError("M6B slave identity rows are invalid")
        if slaves.size and (
            np.any(slaves < 0) or np.any(slaves >= global_row_count)
        ):
            raise ValueError("M6B slave identity rows are out of range")
        expected_slaves = np.setdiff1d(
            np.arange(global_row_count, dtype=np.int64), covered
        )
        if not np.array_equal(np.sort(slaves), expected_slaves):
            raise ValueError("M6B rows and slave identity rows do not partition full space")
        slaves = np.array(np.sort(slaves), dtype=np.int64, order="C", copy=True)
        slaves.setflags(write=False)
        self._slave_rows = slaves
        multiplicity = np.zeros(global_row_count, dtype=np.int32)
        for rows in self._cell_rows:
            np.add.at(multiplicity, rows, 1)
        partition_sum = np.zeros(global_row_count, dtype=np.float64)
        for rows in self._cell_rows:
            np.add.at(partition_sum, rows, 1.0 / multiplicity[rows])
        closure = float(np.max(np.abs(partition_sum[covered] - 1.0)))
        if not np.isfinite(closure) or closure > M6B_POU_CLOSURE_LIMIT:
            raise ValueError("M6B additive PoU closure failed")
        multiplicity.setflags(write=False)
        self._multiplicity = multiplicity
        self._pou_closure_error = closure
        self._audit = self._make_audit(store_audit)

    def _make_audit(self, store_audit: Mapping[str, Any]) -> dict[str, Any]:
        max_cell = max(rows.size for rows in self._cell_rows)
        batched_cell_bytes = int(
            3
            * self._max_factor_multiplicity
            * max_cell
            * _COMPLEX128_BYTES
        )
        bounded_work = int(
            4 * self._global_row_count * _COMPLEX128_BYTES
            + batched_cell_bytes
            + int(store_audit["max_transient_solve_factor_bytes"])
        )
        materialization = {
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab": False,
            "schur": False,
            "slab_factor": False,
        }
        return {
            "schema": M6B_SHIFTED_PC_SCHEMA,
            "beta": self._beta,
            "global_row_count": self._global_row_count,
            "cell_count": self._cell_count,
            "unique_factor_count": int(store_audit["factor_count"]),
            "factor_reuse_count": self._cell_count - int(store_audit["factor_count"]),
            "solve_count_per_apply": len(self._factor_cell_groups),
            "rhs_count": self._cell_count,
            "factor_reuse_exercised": self._cell_count - len(self._factor_cell_groups),
            "factor_copy_count": 0,
            "per_cell_solution_retained": False,
            "partition_of_unity_closure_error": self._pou_closure_error,
            "retained_shifted_factor_payload_bytes": int(
                store_audit["factor_payload_bytes"]
            ),
            "retained_store_total_bytes": int(store_audit["retained_total_bytes"]),
            "bounded_apply_workspace_bytes": bounded_work,
            "workspace_components": {
                "four_full_space_vectors_bytes": int(
                    4 * self._global_row_count * _COMPLEX128_BYTES
                ),
                "batched_cell_rhs_solution_returned_copy_bytes": batched_cell_bytes,
                "max_factor_multiplicity": self._max_factor_multiplicity,
                "one_transient_lu_factor_bytes": int(
                    store_audit["max_transient_solve_factor_bytes"]
                ),
            },
            "retained_plus_work_bytes": int(store_audit["retained_total_bytes"] + bounded_work),
            "fine_space": "uncondensed_fullspace",
            "ordinary_default_changed": False,
            "materialization_identity": materialization,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return dict(self._audit)

    @property
    def multiplicity(self) -> np.ndarray:
        return self._multiplicity.copy()

    def _build_additive_correction(self, rhs: np.ndarray) -> np.ndarray:
        correction = np.zeros(self._global_row_count, dtype=np.complex128)
        for factor_id, cell_ids in enumerate(self._factor_cell_groups):
            factor = self._store.factors[factor_id]
            local_rhs = np.empty(
                (factor.n, len(cell_ids)), dtype=np.complex128, order="C"
            )
            for column, cell_id in enumerate(cell_ids):
                local_rhs[:, column] = self._store.gather(rhs, cell_id)
            local_solution = factor.solve(local_rhs)
            if (
                local_solution.dtype != np.dtype(np.complex128)
                or local_solution.shape != local_rhs.shape
                or not np.all(np.isfinite(local_solution))
            ):
                raise ValueError("M6B shifted LU solve returned invalid values")
            for column, cell_id in enumerate(cell_ids):
                rows = self._cell_rows[cell_id]
                correction[rows] += local_solution[:, column] / self._multiplicity[rows]
            del local_rhs, local_solution
        if self._slave_rows.size:
            correction[self._slave_rows] = rhs[self._slave_rows]
        return correction

    def _apply_core(
        self, rhs: np.ndarray, *, with_measurement: bool
    ) -> tuple[np.ndarray, dict[str, Any] | None]:
        residual_rhs = _finite_vector(rhs, self._global_row_count, "RHS")
        z0 = self._build_additive_correction(residual_rhs)
        q = np.asarray(self._shifted_action(z0), dtype=np.complex128)
        if (
            q.ndim != 1
            or q.size != self._global_row_count
            or not q.flags.c_contiguous
            or not np.all(np.isfinite(q))
        ):
            raise ValueError("M6B shifted action returned an invalid vector")
        denominator = np.vdot(q, q)
        if not np.isfinite(denominator.real) or not np.isfinite(denominator.imag):
            raise FloatingPointError("M6B shifted action denominator is nonfinite")
        if denominator == 0.0:
            raise FloatingPointError("M6B shifted action has zero norm")
        omega = complex(np.vdot(q, residual_rhs) / denominator)
        correction = np.ascontiguousarray(omega * z0, dtype=np.complex128)
        if not with_measurement:
            return correction, None
        rhs_norm = float(np.linalg.norm(residual_rhs))
        rho_unit = float(
            np.linalg.norm(residual_rhs - q)
            / max(rhs_norm, np.finfo(float).tiny)
        )
        residual = np.ascontiguousarray(residual_rhs - omega * q, dtype=np.complex128)
        rho_star = float(np.linalg.norm(residual) / max(rhs_norm, np.finfo(float).tiny))
        measurement = {
            "schema": M6B_SHIFTED_PC_SCHEMA,
            "rhs_sha256": _array_sha256(residual_rhs),
            "correction0_sha256": _array_sha256(z0),
            "action_sha256": _array_sha256(q),
            "correction_sha256": _array_sha256(correction),
            "residual_sha256": _array_sha256(residual),
            "omega": [float(omega.real), float(omega.imag)],
            "rho_unit": rho_unit,
            "rho_star": rho_star,
            "finite": bool(
                np.all(np.isfinite(z0))
                and np.all(np.isfinite(q))
                and np.all(np.isfinite(correction))
                and np.all(np.isfinite(residual))
            ),
            "exact_shifted_action_count": 1,
            "partition_of_unity_closure_error": self._pou_closure_error,
        }
        return correction, measurement

    def apply_with_measurement(
        self, rhs: np.ndarray
    ) -> tuple[np.ndarray, dict[str, Any]]:
        correction, measurement = self._apply_core(rhs, with_measurement=True)
        assert measurement is not None
        return correction, measurement

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        correction, _measurement = self._apply_core(rhs, with_measurement=False)
        return correction


class H2BM6BShiftedRangePC:
    """Fixed W2 local-then-range residual diagnostic composition.

    The production path has exactly three numerical operations: one beta=1
    local correction, one physical outer action on that correction, and one
    ``A^H`` range correction of the resulting residual.  The richer
    ``apply_with_measurement`` method is deliberately diagnostic-only and
    performs the additional fixed probes needed to report the W2 evidence.
    """

    def __init__(
        self,
        local_pc: H2BM6BShiftedPatchPC,
        range_carrier: SparseM6BRangeCarrier,
        physical_outer_action: Callable[[np.ndarray], np.ndarray],
        *,
        global_row_count: int,
        task037_extra_m6b: bool = False,
    ) -> None:
        if task037_extra_m6b is not True:
            raise ValueError("M6B W2 requires explicit research opt-in")
        if not isinstance(local_pc, H2BM6BShiftedPatchPC):
            raise TypeError("M6B W2 requires the shifted local PC")
        if not isinstance(range_carrier, SparseM6BRangeCarrier):
            raise TypeError("M6B W2 requires the sparse range carrier")
        if type(global_row_count) is not int or global_row_count <= 0:
            raise ValueError("M6B W2 global row count is invalid")
        if not callable(physical_outer_action):
            raise TypeError("M6B W2 requires a physical outer action")
        range_audit = range_carrier.audit
        local_audit = local_pc.audit
        if (
            range_carrier.global_rows != global_row_count
            or range_audit["mpi_scope"] != "MPI1"
            or range_audit["dense_nrows_x_columns_retained"] is not False
            or range_audit["az_v_retained"] is not False
            or range_audit["retained_az_bytes"] != 0
            or local_audit["fine_space"] != "uncondensed_fullspace"
            or local_audit["beta"] != 1.0
        ):
            raise ValueError("M6B W2 carrier identity is not closed")
        self._local_pc = local_pc
        self._range_carrier = range_carrier
        self._physical_outer_action = physical_outer_action
        self._global_row_count = global_row_count
        self._apply_count = 0
        self._audit = self._make_audit(local_audit, range_audit)

    def _make_audit(
        self,
        local_audit: Mapping[str, Any],
        range_audit: Mapping[str, Any],
    ) -> dict[str, Any]:
        local_retained = int(local_audit["retained_store_total_bytes"])
        range_retained = int(range_audit["retained_total_bytes"])
        local_work = int(local_audit["bounded_apply_workspace_bytes"])
        range_work = int(range_audit["bounded_work_bytes"])
        composition_incremental = int(
            2 * self._global_row_count * _COMPLEX128_BYTES
        )
        retained = local_retained + range_retained
        range_plus_composition = range_work + composition_incremental
        bounded = max(local_work, range_plus_composition)
        return {
            "schema": M6B_W2_RANGE_PC_SCHEMA,
            "task037_extra_m6b": True,
            "fixed_order": "local_then_physical_residual_then_range",
            "scan": False,
            "global_row_count": self._global_row_count,
            "fine_space": "uncondensed_fullspace",
            "local_beta": float(local_audit["beta"]),
            "local_retained_payload_bytes": local_retained,
            "range_retained_payload_bytes": range_retained,
            "local_bounded_work_bytes": local_work,
            "range_bounded_work_bytes": range_work,
            "range_plus_composition_bounded_work_bytes": range_plus_composition,
            "composition_incremental_bytes": composition_incremental,
            "composition_incremental_is_derived": True,
            "retained_payload_bytes": retained,
            "bounded_work_bytes": bounded,
            "retained_plus_work_bytes": retained + bounded,
            "memory_prediction_is_measurement": False,
            "range_retained_plus_work_bytes": int(
                range_audit["retained_plus_work_bytes"]
            ),
            "production_action_counts": {
                "local_apply": 1,
                "physical_outer_action": 1,
                "range_apply": 1,
            },
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "schur": False,
            "slab_factor": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "ordinary_default_changed": False,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return dict(self._audit)

    @property
    def apply_count(self) -> int:
        return self._apply_count

    def _physical_action(self, values: np.ndarray) -> np.ndarray:
        result = np.asarray(self._physical_outer_action(values))
        return _finite_vector(result, self._global_row_count, "physical outer action")

    def _apply_core(self, rhs: np.ndarray) -> np.ndarray:
        residual_rhs = _finite_vector(rhs, self._global_row_count, "W2 RHS")
        local = np.ascontiguousarray(
            self._local_pc.apply(residual_rhs), dtype=np.complex128
        )
        local_action = self._physical_action(local)
        local_residual = np.ascontiguousarray(
            residual_rhs - local_action, dtype=np.complex128
        )
        del local_action
        coarse = np.ascontiguousarray(
            self._range_carrier.apply(local_residual), dtype=np.complex128
        )
        np.add(local, coarse, out=local)
        del coarse, local_residual
        self._apply_count += 1
        return local

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Apply the fixed local -> physical residual -> range composition."""

        return self._apply_core(rhs)

    def apply_with_measurement(
        self, rhs: np.ndarray
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Run the fixed W2 measurement probes without retaining their arrays."""

        residual_rhs = _finite_vector(rhs, self._global_row_count, "W2 RHS")
        rhs_norm = float(np.linalg.norm(residual_rhs))
        norm_scale = max(rhs_norm, np.finfo(float).tiny)
        local = np.ascontiguousarray(
            self._local_pc.apply(residual_rhs), dtype=np.complex128
        )
        local_action = self._physical_action(local)
        local_residual = np.ascontiguousarray(
            residual_rhs - local_action, dtype=np.complex128
        )
        local_rho = float(np.linalg.norm(local_residual) / norm_scale)

        range_only = np.ascontiguousarray(
            self._range_carrier.apply(residual_rhs), dtype=np.complex128
        )
        range_only_action = self._physical_action(range_only)
        range_only_residual = np.ascontiguousarray(
            residual_rhs - range_only_action, dtype=np.complex128
        )
        range_only_rho = float(np.linalg.norm(range_only_residual) / norm_scale)

        coarse = np.ascontiguousarray(
            self._range_carrier.apply(local_residual), dtype=np.complex128
        )
        coarse_action = self._physical_action(coarse)
        final = np.array(local, dtype=np.complex128, copy=True)
        np.add(final, coarse, out=final)
        final_action = self._physical_action(final)
        final_residual = np.ascontiguousarray(
            residual_rhs - final_action, dtype=np.complex128
        )
        composed_rho = float(np.linalg.norm(final_residual) / norm_scale)
        linear_closure = float(
            np.linalg.norm(final_action - local_action - coarse_action)
            / max(float(np.linalg.norm(final_action)), np.finfo(float).tiny)
        )
        final_range = np.ascontiguousarray(
            self._range_carrier.apply(final_residual), dtype=np.complex128
        )
        final_range_action = self._physical_action(final_range)
        normal_ratio = float(np.linalg.norm(final_range_action) / norm_scale)
        arrays = (
            residual_rhs,
            local,
            local_action,
            local_residual,
            range_only,
            range_only_action,
            range_only_residual,
            coarse,
            coarse_action,
            final_action,
            final_residual,
            final_range,
            final_range_action,
        )
        finite = bool(all(np.all(np.isfinite(value)) for value in arrays))
        measurement = {
            "schema": M6B_W2_RANGE_PC_SCHEMA,
            "finite": finite,
            "rhs_sha256": _array_sha256(residual_rhs),
            "local_correction_sha256": _array_sha256(local),
            "local_action_sha256": _array_sha256(local_action),
            "local_residual_sha256": _array_sha256(local_residual),
            "range_only_correction_sha256": _array_sha256(range_only),
            "range_only_action_sha256": _array_sha256(range_only_action),
            "range_correction_sha256": _array_sha256(coarse),
            "range_action_sha256": _array_sha256(coarse_action),
            "final_correction_sha256": _array_sha256(final),
            "final_action_sha256": _array_sha256(final_action),
            "final_residual_sha256": _array_sha256(final_residual),
            "final_range_correction_sha256": _array_sha256(final_range),
            "final_range_action_sha256": _array_sha256(final_range_action),
            "rho_local_only": local_rho,
            "rho_range_only": range_only_rho,
            "rho_composed": composed_rho,
            "linear_action_closure": linear_closure,
            "normal_projected_component_ratio": normal_ratio,
            "norms": {
                "rhs": rhs_norm,
                "local_correction": float(np.linalg.norm(local)),
                "range_correction": float(np.linalg.norm(coarse)),
                "composed_correction": float(np.linalg.norm(final)),
                "final_residual": float(np.linalg.norm(final_residual)),
                "final_range_action": float(np.linalg.norm(final_range_action)),
            },
            "action_counts": {
                "local_apply": 1,
                "physical_outer_action": 5,
                "range_apply": 3,
            },
            "production_action_counts": dict(
                self._audit["production_action_counts"]
            ),
        }
        del arrays
        self._apply_count += 1
        return final, measurement


class H2BM6BProjectedRangePC:
    """Fixed W2R range-complement residual-minimizing composition.

    For ``l=L_beta(r)``, ``p=A l`` and ``C`` the fixed ``A^H`` range
    carrier, this class forms ``c_r=C(r)``, ``c_p=C(p)`` and minimizes the
    residual on the complement of ``range(AZ)`` with one complex scalar.
    The production path uses one local solve, three physical actions and two
    range actions; diagnostic probes add only the fixed final closure actions.
    """

    def __init__(
        self,
        local_pc: H2BM6BShiftedPatchPC,
        range_carrier: SparseM6BRangeCarrier,
        physical_outer_action: Callable[[np.ndarray], np.ndarray],
        *,
        global_row_count: int,
        task037_extra_m6b: bool = False,
        expected_local_beta: float = 1.0,
    ) -> None:
        if task037_extra_m6b is not True:
            raise ValueError("M6B W2R requires explicit research opt-in")
        if not isinstance(local_pc, H2BM6BShiftedPatchPC):
            raise TypeError("M6B W2R requires the shifted local PC")
        if not isinstance(range_carrier, SparseM6BRangeCarrier):
            raise TypeError("M6B W2R requires the sparse range carrier")
        if type(global_row_count) is not int or global_row_count <= 0:
            raise ValueError("M6B W2R global row count is invalid")
        if not callable(physical_outer_action):
            raise TypeError("M6B W2R requires a physical outer action")
        if expected_local_beta not in M6B_ALLOWED_SHIFTED_BETAS:
            raise ValueError("M6B W2R expected beta is not fixed")
        local_audit = local_pc.audit
        range_audit = range_carrier.audit
        if (
            range_carrier.global_rows != global_row_count
            or range_audit.get("mpi_scope") != "MPI1"
            or range_audit.get("dense_nrows_x_columns_retained") is not False
            or range_audit.get("az_v_retained") is not False
            or range_audit.get("retained_az_bytes") != 0
            or local_audit.get("fine_space") != "uncondensed_fullspace"
            or local_audit.get("beta") != expected_local_beta
        ):
            raise ValueError("M6B W2R carrier identity is not closed")
        self._local_pc = local_pc
        self._range_carrier = range_carrier
        self._physical_outer_action = physical_outer_action
        self._global_row_count = global_row_count
        self._apply_count = 0
        self._audit = self._make_audit(local_audit, range_audit)

    def _make_audit(
        self,
        local_audit: Mapping[str, Any],
        range_audit: Mapping[str, Any],
    ) -> dict[str, Any]:
        local_retained = int(local_audit["retained_store_total_bytes"])
        range_retained = int(range_audit["retained_total_bytes"])
        local_work = int(local_audit["bounded_apply_workspace_bytes"])
        range_work = int(range_audit["bounded_work_bytes"])
        projected_full_vectors = 8
        full_vector_bytes = int(self._global_row_count * _COMPLEX128_BYTES)
        projected_incremental = projected_full_vectors * full_vector_bytes
        retained = local_retained + range_retained
        bounded = max(local_work, range_work + projected_incremental)
        return {
            "schema": M6B_W2R_RANGE_PC_SCHEMA,
            "task037_extra_m6b": True,
            "fixed_order": "projected_range_complement",
            "scan": False,
            "global_row_count": self._global_row_count,
            "fine_space": "uncondensed_fullspace",
            "local_beta": float(local_audit["beta"]),
            "local_retained_payload_bytes": local_retained,
            "range_retained_payload_bytes": range_retained,
            "local_bounded_work_bytes": local_work,
            "range_bounded_work_bytes": range_work,
            "projected_full_vector_count": projected_full_vectors,
            "projected_full_vector_bytes": full_vector_bytes,
            "projected_incremental_bytes": projected_incremental,
            "retained_payload_bytes": retained,
            "bounded_work_bytes": bounded,
            "retained_plus_work_bytes": retained + bounded,
            "memory_prediction_is_measurement": False,
            "production_action_counts": {
                "local_apply": 1,
                "physical_outer_action": 3,
                "range_apply": 2,
            },
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "schur": False,
            "slab_factor": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "ordinary_default_changed": False,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return dict(self._audit)

    @property
    def apply_count(self) -> int:
        return self._apply_count

    def _physical_action(self, values: np.ndarray) -> np.ndarray:
        result = np.asarray(self._physical_outer_action(values))
        return _finite_vector(result, self._global_row_count, "physical outer action")

    @staticmethod
    def _projected_alpha(
        p_perp: np.ndarray, r_perp: np.ndarray
    ) -> tuple[complex, complex]:
        denominator = complex(np.vdot(p_perp, p_perp))
        if (
            not np.isfinite(denominator.real)
            or not np.isfinite(denominator.imag)
            or denominator == 0.0
        ):
            raise FloatingPointError("M6B W2R projected denominator is invalid")
        alpha = complex(np.vdot(p_perp, r_perp) / denominator)
        if not np.isfinite(alpha.real) or not np.isfinite(alpha.imag):
            raise FloatingPointError("M6B W2R projected alpha is nonfinite")
        return alpha, denominator

    def _apply_production(self, rhs: np.ndarray) -> np.ndarray:
        residual_rhs = _finite_vector(rhs, self._global_row_count, "W2R RHS")
        local = np.ascontiguousarray(
            self._local_pc.apply(residual_rhs), dtype=np.complex128
        )
        local = _finite_vector(local, self._global_row_count, "W2R local correction")
        local_action = self._physical_action(local)
        range_rhs = np.ascontiguousarray(
            self._range_carrier.apply(residual_rhs), dtype=np.complex128
        )
        range_action = self._physical_action(range_rhs)
        range_local_rhs = np.ascontiguousarray(
            self._range_carrier.apply(local_action), dtype=np.complex128
        )
        range_local_action = self._physical_action(range_local_rhs)
        np.subtract(residual_rhs, range_action, out=range_action)
        np.subtract(local_action, range_local_action, out=range_local_action)
        alpha, _denominator = self._projected_alpha(
            range_local_action, range_action
        )
        np.multiply(local, alpha, out=local)
        correction = np.array(range_rhs, dtype=np.complex128, copy=True)
        np.add(correction, local, out=correction)
        np.multiply(range_local_rhs, alpha, out=range_local_rhs)
        np.subtract(correction, range_local_rhs, out=correction)
        correction = _finite_vector(
            correction, self._global_row_count, "W2R correction"
        )
        self._apply_count += 1
        return correction

    def _apply_diagnostic_core(
        self, rhs: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        residual_rhs = _finite_vector(rhs, self._global_row_count, "W2R RHS")
        local = np.ascontiguousarray(
            self._local_pc.apply(residual_rhs), dtype=np.complex128
        )
        local = _finite_vector(local, self._global_row_count, "W2R local correction")
        local_action = self._physical_action(local)
        range_rhs = np.ascontiguousarray(
            self._range_carrier.apply(residual_rhs), dtype=np.complex128
        )
        range_action = self._physical_action(range_rhs)
        range_local_rhs = np.ascontiguousarray(
            self._range_carrier.apply(local_action), dtype=np.complex128
        )
        range_local_action = self._physical_action(range_local_rhs)
        r_perp = np.ascontiguousarray(
            residual_rhs - range_action, dtype=np.complex128
        )
        p_perp = np.ascontiguousarray(
            local_action - range_local_action, dtype=np.complex128
        )
        alpha, denominator = self._projected_alpha(p_perp, r_perp)
        correction = np.ascontiguousarray(
            alpha * local + range_rhs - alpha * range_local_rhs,
            dtype=np.complex128,
        )
        correction = _finite_vector(
            correction, self._global_row_count, "W2R correction"
        )
        represented = np.ascontiguousarray(
            alpha * local_action + range_action - alpha * range_local_action,
            dtype=np.complex128,
        )
        represented = _finite_vector(
            represented, self._global_row_count, "W2R represented action"
        )
        self._apply_count += 1
        core = {
            "alpha": alpha,
            "denominator": denominator,
            "local": local,
            "local_action": local_action,
            "range_rhs": range_rhs,
            "range_action": range_action,
            "range_local_rhs": range_local_rhs,
            "range_local_action": range_local_action,
            "r_perp": r_perp,
            "p_perp": p_perp,
            "rhs": residual_rhs,
        }
        return correction, represented, core

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        return self._apply_production(rhs)

    def apply_with_measurement(
        self, rhs: np.ndarray
    ) -> tuple[np.ndarray, dict[str, Any]]:
        correction, represented, core = self._apply_diagnostic_core(rhs)
        residual_rhs = core["rhs"]
        actual_action = self._physical_action(correction)
        final_residual = np.ascontiguousarray(
            residual_rhs - actual_action, dtype=np.complex128
        )
        final_range_rhs = np.ascontiguousarray(
            self._range_carrier.apply(final_residual), dtype=np.complex128
        )
        final_range_action = self._physical_action(final_range_rhs)
        rhs_norm = float(np.linalg.norm(residual_rhs))
        norm_scale = max(rhs_norm, np.finfo(float).tiny)
        p_norm = float(np.linalg.norm(core["p_perp"]))
        optimality = float(
            abs(np.vdot(core["p_perp"], final_residual))
            / max(p_norm * norm_scale, np.finfo(float).tiny)
        )
        action_closure = float(
            np.linalg.norm(actual_action - represented)
            / max(float(np.linalg.norm(actual_action)), np.finfo(float).tiny)
        )
        arrays = (
            correction,
            represented,
            actual_action,
            final_residual,
            final_range_rhs,
            final_range_action,
        )
        finite = bool(all(np.all(np.isfinite(value)) for value in arrays))
        measurement = {
            "schema": M6B_W2R_RANGE_PC_SCHEMA,
            "finite": finite,
            "rhs_sha256": _array_sha256(residual_rhs),
            "local_correction_sha256": _array_sha256(core["local"]),
            "local_action_sha256": _array_sha256(core["local_action"]),
            "range_only_correction_sha256": _array_sha256(core["range_rhs"]),
            "range_only_action_sha256": _array_sha256(core["range_action"]),
            "range_correction_sha256": _array_sha256(core["range_local_rhs"]),
            "range_action_sha256": _array_sha256(core["range_local_action"]),
            "correction_sha256": _array_sha256(correction),
            "final_correction_sha256": _array_sha256(correction),
            "represented_action_sha256": _array_sha256(represented),
            "final_action_sha256": _array_sha256(actual_action),
            "final_residual_sha256": _array_sha256(final_residual),
            "final_range_correction_sha256": _array_sha256(final_range_rhs),
            "final_range_action_sha256": _array_sha256(final_range_action),
            "rho_local_only": float(
                np.linalg.norm(residual_rhs - core["local_action"]) / norm_scale
            ),
            "rho_range_only": float(
                np.linalg.norm(residual_rhs - core["range_action"]) / norm_scale
            ),
            "rho_projected": float(np.linalg.norm(final_residual) / norm_scale),
            "linear_action_closure": action_closure,
            "normal_projected_component_ratio": float(
                np.linalg.norm(final_range_action) / norm_scale
            ),
            "complement_optimality": optimality,
            "alpha": [float(core["alpha"].real), float(core["alpha"].imag)],
            "projection_denominator": [
                float(core["denominator"].real),
                float(core["denominator"].imag),
            ],
            "norms": {
                "rhs": rhs_norm,
                "p_perp": p_norm,
                "final_residual": float(np.linalg.norm(final_residual)),
                "final_range_action": float(np.linalg.norm(final_range_action)),
            },
            "action_counts": {
                "local_apply": 1,
                "physical_outer_action": 5,
                "range_apply": 3,
            },
            "production_action_counts": dict(
                self._audit["production_action_counts"]
            ),
        }
        del arrays, core
        return correction, measurement


class M6BShiftedPCContext:
    """PETSc Python-PC adapter borrowing source values for one synchronous apply."""

    def __init__(self, pc: H2BM6BShiftedPatchPC) -> None:
        self._pc = pc
        self._apply_count = 0
        self._last_measurement: dict[str, Any] | None = None

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        # The core apply is synchronous and does not retain this borrowed array.
        values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        correction = self._pc.apply(values)
        if target.getLocalSize() != correction.size:
            raise ValueError("M6B PC target ownership differs from correction")
        np.copyto(target.getArray(), correction)
        target.assemble()
        self._apply_count += 1
        self._last_measurement = None

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def audit(self) -> dict[str, Any]:
        return {
            **self._pc.audit,
            "pc_python": True,
            "pc_side": "right",
            "apply_count": self._apply_count,
            "last_measurement": self._last_measurement,
        }


class M6BOuterMatPythonContext:
    """One matrix-free outer ``A_volume + A_DtN`` MatPython action."""

    def __init__(
        self,
        volume_action: Any,
        dtn_action: Any,
        *,
        owned_rows: int,
        global_rows: int,
        volume_hermitian_action: Any | None = None,
    ) -> None:
        if not callable(getattr(volume_action, "mult", None)):
            raise TypeError("M6B volume action must provide mult")
        if not callable(getattr(dtn_action, "apply", None)):
            raise TypeError("M6B DtN action must provide apply")
        if volume_hermitian_action is not None and not callable(
            getattr(volume_hermitian_action, "mult", None)
        ):
            raise TypeError("M6B adjoint volume action must provide mult")
        self._volume_action = volume_action
        self._volume_hermitian_action = volume_hermitian_action
        self._dtn_action = dtn_action
        self._owned_rows = int(owned_rows)
        self._global_rows = int(global_rows)
        self._dtn_work: PETSc.Vec | None = None
        self._apply_count = 0
        self._hermitian_apply_count = 0

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if source.getLocalSize() != self._owned_rows or source.getSize() != self._global_rows:
            raise ValueError("M6B outer source layout is invalid")
        if target.getLocalSize() != self._owned_rows:
            raise ValueError("M6B outer target layout is invalid")
        if self._dtn_work is None:
            self._dtn_work = source.duplicate()
        volume_result = self._volume_action.mult(source)
        volume_values = np.asarray(
            volume_result.getArray(readonly=True), dtype=np.complex128
        )
        if volume_values.size != self._owned_rows or not np.all(np.isfinite(volume_values)):
            raise ValueError("M6B volume action returned an invalid owned layout")
        target_values = target.getArray()
        np.copyto(target_values, volume_values)
        self._dtn_action.apply(source, self._dtn_work)
        dtn_values = np.asarray(
            self._dtn_work.getArray(readonly=True), dtype=np.complex128
        )
        if dtn_values.size != self._owned_rows or not np.all(np.isfinite(dtn_values)):
            raise ValueError("M6B outer action returned an invalid owned layout")
        target_values += dtn_values
        target.assemble()
        # Both action outputs are borrowed; only target retains the result.
        del volume_result, volume_values, dtn_values, target_values
        self._apply_count += 1

    def apply_hermitian(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._volume_hermitian_action is None:
            raise RuntimeError("M6B adjoint volume action is not configured")
        if not callable(getattr(self._dtn_action, "apply_hermitian", None)):
            raise RuntimeError("M6B DtN action does not provide apply_hermitian")
        if source.getLocalSize() != self._owned_rows or source.getSize() != self._global_rows:
            raise ValueError("M6B adjoint outer source layout is invalid")
        if target.getLocalSize() != self._owned_rows:
            raise ValueError("M6B adjoint outer target layout is invalid")
        if self._dtn_work is None:
            self._dtn_work = source.duplicate()
        volume_result = self._volume_hermitian_action.mult(source)
        volume_values = np.asarray(
            volume_result.getArray(readonly=True), dtype=np.complex128
        )
        if volume_values.size != self._owned_rows or not np.all(np.isfinite(volume_values)):
            raise ValueError("M6B adjoint volume action returned an invalid layout")
        target_values = target.getArray()
        np.copyto(target_values, volume_values)
        self._dtn_action.apply_hermitian(source, self._dtn_work)
        dtn_values = np.asarray(
            self._dtn_work.getArray(readonly=True), dtype=np.complex128
        )
        if dtn_values.size != self._owned_rows or not np.all(np.isfinite(dtn_values)):
            raise ValueError("M6B adjoint DtN action returned an invalid layout")
        target_values += dtn_values
        target.assemble()
        del volume_result, volume_values, dtn_values, target_values
        self._hermitian_apply_count += 1

    def multHermitian(
        self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        self.apply_hermitian(source, target)

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": M6B_SHIFTED_PC_SCHEMA,
            "matrix_type": "python_action_only",
            "global_matrix": False,
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "owned_rows": self._owned_rows,
            "global_rows": self._global_rows,
            "apply_count": self._apply_count,
            "hermitian_action_available": self._volume_hermitian_action is not None,
            "hermitian_apply_count": self._hermitian_apply_count,
        }

    def destroy(self, _matrix: Any = None) -> None:
        if self._dtn_work is not None:
            self._dtn_work.destroy()
            self._dtn_work = None


class M6BNumpyOuterActionBridge:
    """Reuse fixed PETSc work vectors for synchronous NumPy outer actions.

    The returned NumPy array is a copy of the PETSc target.  The source and
    target vectors are owned by this bridge and are borrowed only during one
    call; no action-owned borrowed output is destroyed here.
    """

    def __init__(
        self,
        context: M6BOuterMatPythonContext,
        template: PETSc.Vec,
    ) -> None:
        if not isinstance(context, M6BOuterMatPythonContext):
            raise TypeError("M6B NumPy bridge requires the outer context")
        self._context = context
        self._source = template.duplicate()
        self._target = template.duplicate()
        self._local_rows = int(template.getLocalSize())
        self._global_rows = int(template.getSize())
        self._apply_count = 0
        self._hermitian_apply_count = 0
        self._vector_create_count = 2
        self._destroyed = False

    def _input(self, values: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("M6B NumPy outer bridge is destroyed")
        array = np.asarray(values, dtype=np.complex128)
        if (
            array.ndim != 1
            or array.size != self._local_rows
            or not np.all(np.isfinite(array))
        ):
            raise ValueError("M6B NumPy outer bridge input has invalid layout")
        np.copyto(self._source.getArray(), array)
        return array

    def apply(self, values: np.ndarray) -> np.ndarray:
        self._input(values)
        self._context.mult(None, self._source, self._target)
        result = np.array(
            self._target.getArray(readonly=True), dtype=np.complex128, copy=True
        )
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("M6B NumPy outer action is nonfinite")
        self._apply_count += 1
        return result

    def apply_hermitian(self, values: np.ndarray) -> np.ndarray:
        self._input(values)
        self._context.apply_hermitian(self._source, self._target)
        result = np.array(
            self._target.getArray(readonly=True), dtype=np.complex128, copy=True
        )
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("M6B NumPy adjoint action is nonfinite")
        self._hermitian_apply_count += 1
        return result

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": "task037.extra.m6b.numpy-outer-bridge.v1",
            "owned_rows": self._local_rows,
            "global_rows": self._global_rows,
            "vector_create_count": self._vector_create_count,
            "forward_apply_count": self._apply_count,
            "hermitian_apply_count": self._hermitian_apply_count,
            "fixed_work_vectors": 2,
            "per_apply_vec_creation": 0,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._target.destroy()
        self._source.destroy()
        self._destroyed = True


def build_m6b_outer_mat(
    volume_action: Any,
    dtn_action: Any,
    *,
    owned_rows: int,
    global_rows: int,
    comm: Any,
    volume_hermitian_action: Any | None = None,
) -> tuple[PETSc.Mat, M6BOuterMatPythonContext]:
    context = M6BOuterMatPythonContext(
        volume_action,
        dtn_action,
        owned_rows=owned_rows,
        global_rows=global_rows,
        volume_hermitian_action=volume_hermitian_action,
    )
    matrix = PETSc.Mat().createPython(
        ((owned_rows, global_rows), (owned_rows, global_rows)),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    return matrix, context


def compose_m6b_physical_rhs(
    dtn_action: Any,
    base_incident_traction: PETSc.Vec,
    mode_amplitudes: np.ndarray,
    target: PETSc.Vec,
) -> None:
    """Compose the complete load: base top traction plus the modal term."""

    if not callable(getattr(dtn_action, "compose_physical_rhs", None)):
        raise TypeError("M6B physical RHS requires the full-space DtN action")
    amplitudes = np.asarray(mode_amplitudes, dtype=np.complex128)
    if amplitudes.ndim != 1 or not np.all(np.isfinite(amplitudes)):
        raise ValueError("M6B incident amplitudes are invalid")
    dtn_action.compose_physical_rhs(base_incident_traction, amplitudes, target)


def recover_m6b_auxiliary(dtn_action: Any, volume_solution: PETSc.Vec) -> np.ndarray:
    """Return the fixed auxiliary recovery ``a=-D u``."""

    if not callable(getattr(dtn_action, "recover_auxiliary", None)):
        raise TypeError("M6B auxiliary recovery requires the full-space DtN action")
    return np.asarray(dtn_action.recover_auxiliary(volume_solution), dtype=np.complex128)


class M6BScreenCheckpointWriter:
    """Write only the four fixed true-residual checkpoint vectors."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = Path(run_dir)
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def _write(self, path: Path, values: np.ndarray) -> dict[str, Any]:
        array = _finite_vector(values, int(np.asarray(values).size), path.name)
        np.save(path, np.ascontiguousarray(array), allow_pickle=False)
        return {
            "path": path.name,
            "bytes": int(path.stat().st_size),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "array_sha256": _array_sha256(array),
            "shape": [int(value) for value in array.shape],
            "dtype": str(array.dtype),
        }

    def _write_arrays(
        self, iteration: int, arrays: Mapping[str, np.ndarray]
    ) -> dict[str, Any]:
        if iteration not in M6B_FIXED_SCREEN_ITERATIONS:
            raise ValueError("M6B checkpoint iteration is not fixed")
        required = {"solution", "outer_action", "residual", "rhs"}
        if set(arrays) != required:
            raise ValueError("M6B checkpoint arrays are incomplete")
        shape: tuple[int, ...] | None = None
        for name, values in arrays.items():
            array = np.asarray(values)
            if (
                array.ndim != 1
                or array.dtype != np.dtype(np.complex128)
                or not array.flags.c_contiguous
                or (shape is not None and array.shape != shape)
                or not np.all(np.isfinite(array))
            ):
                raise ValueError(f"M6B checkpoint array is invalid: {name}")
            shape = array.shape
        artifacts = {
            name: self._write(
                self._run_dir / f"m6b_iter{iteration}_{name}.npy", values
            )
            for name, values in arrays.items()
        }
        residual = np.asarray(arrays["residual"])
        rhs = np.asarray(arrays["rhs"])
        relative = float(
            np.linalg.norm(residual)
            / max(np.linalg.norm(rhs), np.finfo(float).tiny)
        )
        return {
            "iteration": int(iteration),
            "true_relative_residual": relative,
            "artifacts": artifacts,
        }

    def write_checkpoint(
        self,
        iteration: int,
        *,
        solution: PETSc.Vec,
        outer_action: PETSc.Vec,
        residual: PETSc.Vec,
        rhs: PETSc.Vec,
    ) -> dict[str, Any]:
        arrays = {
            "solution": np.asarray(solution.getArray(readonly=True)),
            "outer_action": np.asarray(outer_action.getArray(readonly=True)),
            "residual": np.asarray(residual.getArray(readonly=True)),
            "rhs": np.asarray(rhs.getArray(readonly=True)),
        }
        return self._write_arrays(iteration, arrays)

    def write_numpy_checkpoint(
        self,
        iteration: int,
        *,
        solution: np.ndarray,
        outer_action: np.ndarray,
        residual: np.ndarray,
        rhs: np.ndarray,
    ) -> dict[str, Any]:
        """Write one checkpoint from the disk-cycle NumPy callback path."""
        arrays = {
            "solution": np.asarray(solution),
            "outer_action": np.asarray(outer_action),
            "residual": np.asarray(residual),
            "rhs": np.asarray(rhs),
        }
        return self._write_arrays(iteration, arrays)


def _m6b_numeric_screen_core(samples: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute only the fixed checkpoint and performance predicates."""

    required = {str(value) for value in M6B_FIXED_SCREEN_ITERATIONS}
    problems: list[str] = []
    values: dict[str, float] = {}
    if not isinstance(samples, Mapping) or set(samples) != required:
        problems.append("checkpoint_set")
    else:
        for key in sorted(required, key=int):
            item = samples[key]
            value = item.get("true_relative_residual") if isinstance(item, Mapping) else None
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not np.isfinite(value)
                or float(value) < 0.0
            ):
                problems.append(f"checkpoint_{key}")
            else:
                values[key] = float(value)
    if not problems:
        if values["20"] > M6B_SCREEN_RHO_LIMITS["iteration20"]:
            problems.append("true_residual_iter20")
        if values["100"] > M6B_SCREEN_RHO_LIMITS["iteration100"]:
            problems.append("true_residual_iter100")
        if values["200"] > M6B_SCREEN_RHO_LIMITS["iteration200"]:
            problems.append("true_residual_iter200")
        improvement = 1.0 - values["200"] / values["150"] if values["150"] > 0.0 else -np.inf
        if not np.isfinite(improvement) or improvement < M6B_IMPROVEMENT_LIMIT:
            problems.append("true_residual_150_to_200_improvement")
    return {
        "pass": not problems,
        "problems": problems,
        "true_residuals": values,
        "improvement_150_to_200": (
            None
            if "150" not in values or "200" not in values
            else 1.0 - values["200"] / values["150"]
        ),
        "limits": {
            **M6B_SCREEN_RHO_LIMITS,
            "improvement_150_to_200": M6B_IMPROVEMENT_LIMIT,
        },
    }


def evaluate_m6b_screen_gate(
    samples: Mapping[str, Any],
    *,
    online_peak_rss_bytes: int,
    online_swap_bytes: int,
    processes_gone: bool,
) -> dict[str, Any]:
    """Recompute numeric and resource gates with missing data failing closed."""

    numeric = _m6b_numeric_screen_core(samples)
    problems = list(numeric["problems"])
    resource = (
        type(online_peak_rss_bytes) is int
        and online_peak_rss_bytes < M6B_ONLINE_RSS_LIMIT_BYTES
        and online_swap_bytes == 0
        and processes_gone is True
    )
    if not resource:
        problems.append("online_resource")
    return {
        "pass": not problems,
        "problems": problems,
        "true_residuals": numeric["true_residuals"],
        "improvement_150_to_200": numeric["improvement_150_to_200"],
        "resource_gate": resource,
        "limits": {
            **numeric["limits"],
            "online_peak_rss_bytes": M6B_ONLINE_RSS_LIMIT_BYTES,
        },
    }


def evaluate_m6b_numeric_screen_gate(samples: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the fixed numeric screen without claiming a resource Gate."""
    result = _m6b_numeric_screen_core(samples)
    result["resource_gate"] = None
    return result


def run_m6b_disk_backed_right_fgmres_screen(
    action: Callable[[np.ndarray], np.ndarray],
    right_pc: Callable[[np.ndarray], np.ndarray],
    rhs: np.ndarray,
    *,
    checkpoint_dir: Path,
    scratch_dir: Path,
    observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the fixed one-cycle disk-backed NumPy screen."""

    from .disk_backed_flexible_gmres import DiskBackedFlexibleGMRES

    rhs = _finite_vector(rhs, int(np.asarray(rhs).size), "disk FGMRES RHS")
    writer = M6BScreenCheckpointWriter(checkpoint_dir)
    samples: dict[str, Any] = {}

    def checkpoint_observer(event: Mapping[str, Any]) -> None:
        iteration = int(event["iteration"])
        checkpoint = writer.write_numpy_checkpoint(
            iteration,
            solution=event["solution"],
            outer_action=event["action"],
            residual=event["residual"],
            rhs=event["rhs"],
        )
        checkpoint["estimated_residual_norm"] = float(
            event["estimated_residual_norm"]
        )
        checkpoint["estimated_residual_is_diagnostic_only"] = True
        samples[str(iteration)] = checkpoint
        if observer is not None:
            observer(
                {
                    "iteration": iteration,
                    "true_relative_residual": checkpoint[
                        "true_relative_residual"
                    ],
                    "estimated_residual_norm": checkpoint[
                        "estimated_residual_norm"
                    ],
                    "estimated_residual_is_diagnostic_only": True,
                    "artifacts": {
                        name: {
                            field: artifact[field]
                            for field in (
                                "path",
                                "bytes",
                                "sha256",
                                "array_sha256",
                            )
                        }
                        for name, artifact in checkpoint["artifacts"].items()
                    },
                }
            )

    solver = DiskBackedFlexibleGMRES(
        action,
        right_pc,
        max_steps=200,
        checkpoints=(20, 100, 150, 200),
    )
    result = solver.solve(
        rhs,
        scratch_dir=scratch_dir,
        observer=checkpoint_observer,
    )
    core_audit = dict(result.audit)
    return {
        "schema": M6B_W5_SCHEMA,
        "rows": int(rhs.size),
        "solver": "disk_backed_flexible_gmres",
        "petsc_ksp_used": False,
        "side": "right",
        "two_pass_mgs": True,
        "cycle": "fixed_one_200_step_cycle",
        "max_steps": 200,
        "iterations": int(result.iterations),
        "checkpoint_iterations": [20, 100, 150, 200],
        "true_residual_authority": "rhs-outer_action",
        "estimated_residual_is_diagnostic_only": True,
        "happy_breakdown": bool(result.happy_breakdown),
        "samples": samples,
        "numeric_gate": evaluate_m6b_numeric_screen_gate(samples),
        "core_audit": core_audit,
        "scratch": {
            "bytes": core_audit["scratch_bytes"],
            "paths": dict(core_audit["scratch_paths"]),
            "mmap": False,
            "basis_in_memory": False,
        },
        "action_count": core_audit["action_count"],
        "pc_count": core_audit["pc_count"],
        "read_write_counts": {
            "v_basis": {
                "read_count": core_audit["v_basis"]["read_count"],
                "write_count": core_audit["v_basis"]["write_count"],
            },
            "z_basis": {
                "read_count": core_audit["z_basis"]["read_count"],
                "write_count": core_audit["z_basis"]["write_count"],
            },
        },
    }


def run_m6b_right_fgmres_screen(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    *,
    pc_context: M6BShiftedPCContext,
    checkpoint_dir: Path,
    operator_context: Any | None = None,
    checkpoint_observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run fixed right-FGMRES and checkpoint explicit true residuals."""

    rows = int(rhs.getSize())
    if operator.getSize() != (rows, rows):
        raise ValueError("M6B outer operator and RHS sizes differ")
    writer = M6BScreenCheckpointWriter(checkpoint_dir)
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    action_work = operator.createVecLeft()
    residual_work = rhs.duplicate()
    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
        raise ValueError("M6B RHS norm must be positive")
    samples: dict[str, Any] = {}
    ksp = PETSc.KSP().create(rhs.getComm())
    try:
        solution.set(0.0)
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(M6B_FIXED_RESTART)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=0.0, atol=0.0, max_it=M6B_FIXED_MAX_IT)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setUp()
        actual_rtol, actual_atol, _actual_dtol, actual_max_it = ksp.getTolerances()

        def sample(current: PETSc.KSP, iteration: int, reported: float) -> None:
            key = str(iteration)
            if iteration not in M6B_FIXED_SCREEN_ITERATIONS or key in samples:
                return
            current.buildSolution(monitor_solution)
            operator.mult(monitor_solution, action_work)
            residual_work.waxpy(PETSc.ScalarType(-1.0), action_work, rhs)
            checkpoint = writer.write_checkpoint(
                iteration,
                solution=monitor_solution,
                outer_action=action_work,
                residual=residual_work,
                rhs=rhs,
            )
            checkpoint["reported_residual"] = (
                float(reported) if np.isfinite(reported) else None
            )
            samples[key] = checkpoint
            if checkpoint_observer is not None:
                checkpoint_observer(
                    {
                        "iteration": checkpoint["iteration"],
                        "true_relative_residual": checkpoint[
                            "true_relative_residual"
                        ],
                        "artifacts": {
                            name: {
                                field: artifact[field]
                                for field in (
                                    "path",
                                    "bytes",
                                    "sha256",
                                    "array_sha256",
                                )
                            }
                            for name, artifact in checkpoint["artifacts"].items()
                        },
                    }
                )

        ksp.setMonitor(
            lambda current, iteration, reported: sample(
                current, int(iteration), float(reported)
            )
        )
        ksp.solve(rhs, solution)
        return {
            "schema": "task037.extra.h2b.m6b.screen.v1",
            "rows": rows,
            "ksp_type": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart_set": M6B_FIXED_RESTART,
            "max_it": M6B_FIXED_MAX_IT,
            "max_it_actual": int(actual_max_it),
            "rtol": float(actual_rtol),
            "atol": float(actual_atol),
            "iterations": int(ksp.getIterationNumber()),
            "converged_reason": int(ksp.getConvergedReason()),
            "samples": samples,
            "fixed_screen": True,
            "operator_apply_count": (
                None if operator_context is None else operator_context.apply_count
            ),
            "pc_apply_count": pc_context.apply_count,
            "sample_action_count": len(samples),
        }
    finally:
        ksp.destroy()
        solution.destroy()
        monitor_solution.destroy()
        action_work.destroy()
        residual_work.destroy()


def run_m6b_right_fbcgs_screen(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    *,
    pc_context: M6BShiftedPCContext,
    checkpoint_dir: Path,
    operator_context: Any | None = None,
    checkpoint_observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run fixed right-FBCGS using the direct KSP solution Vec at checkpoints."""

    rows = int(rhs.getSize())
    if operator.getSize() != (rows, rows):
        raise ValueError("M6B outer operator and RHS sizes differ")
    writer = M6BScreenCheckpointWriter(checkpoint_dir)
    solution = operator.createVecRight()
    action_work = operator.createVecLeft()
    residual_work = rhs.duplicate()
    rhs_norm = float(rhs.norm())
    if not np.isfinite(rhs_norm) or rhs_norm <= 0.0:
        raise ValueError("M6B RHS norm must be positive")
    samples: dict[str, Any] = {}
    operator_apply_count = 0
    ksp = PETSc.KSP().create(rhs.getComm())
    try:
        solution.set(0.0)
        ksp.setOperators(operator)
        ksp.setType("fbcgs")
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(
            rtol=0.0, atol=0.0, max_it=M6B_W4_KSP_ITERATIONS[-1]
        )
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        ksp.setUp()
        actual_rtol, actual_atol, _actual_dtol, actual_max_it = ksp.getTolerances()
        if ksp.getType() != "fbcgs":
            raise ValueError("M6B FBCGS KSP type was not retained")
        if ksp.getPCSide() != PETSc.PC.Side.RIGHT:
            raise ValueError("M6B FBCGS PC side was not retained")
        if ksp.getNormType() != PETSc.KSP.NormType.UNPRECONDITIONED:
            raise ValueError("M6B FBCGS norm type was not retained")
        if float(actual_rtol) != 0.0 or float(actual_atol) != 0.0:
            raise ValueError("M6B FBCGS tolerances were not retained")
        if int(actual_max_it) != M6B_W4_KSP_ITERATIONS[-1]:
            raise ValueError("M6B FBCGS max_it was not retained")

        def sample(_current: PETSc.KSP, iteration: int, reported: float) -> None:
            nonlocal operator_apply_count
            if iteration not in M6B_W4_KSP_TO_PC_BUDGET:
                return
            budget = M6B_W4_KSP_TO_PC_BUDGET[iteration]
            key = str(budget)
            if key in samples:
                return
            if int(pc_context.apply_count) != budget:
                raise ValueError("M6B FBCGS PC apply budget is not closed")
            operator.mult(solution, action_work)
            operator_apply_count += 1
            residual_work.waxpy(PETSc.ScalarType(-1.0), action_work, rhs)
            checkpoint = writer.write_checkpoint(
                budget,
                solution=solution,
                outer_action=action_work,
                residual=residual_work,
                rhs=rhs,
            )
            checkpoint.update(
                {
                    "ksp_iteration": int(iteration),
                    "pc_apply_budget": int(budget),
                    "checkpoint_axis": "pc_apply_budget",
                    "iteration_label_is_pc_apply_budget": True,
                    "reported_residual": (
                        float(reported) if np.isfinite(reported) else None
                    ),
                    "reported_residual_is_diagnostic_only": True,
                    "pc_apply_count": int(pc_context.apply_count),
                }
            )
            samples[key] = checkpoint
            if checkpoint_observer is not None:
                checkpoint_observer(
                    {
                        "iteration": int(budget),
                        "ksp_iteration": int(iteration),
                        "pc_apply_budget": int(budget),
                        "true_relative_residual": checkpoint[
                            "true_relative_residual"
                        ],
                        "artifacts": {
                            name: {
                                field: artifact[field]
                                for field in (
                                    "path",
                                    "bytes",
                                    "sha256",
                                    "array_sha256",
                                )
                            }
                            for name, artifact in checkpoint["artifacts"].items()
                        },
                    }
                )

        ksp.setMonitor(
            lambda current, iteration, reported: sample(
                current, int(iteration), float(reported)
            )
        )
        ksp.solve(rhs, solution)
        actual_iterations = int(ksp.getIterationNumber())
        sample(ksp, actual_iterations, float(ksp.getResidualNorm()))
        expected_pc_applies = 2 * actual_iterations
        if set(samples) != {str(value) for value in M6B_W4_PC_APPLY_BUDGETS}:
            raise ValueError("M6B FBCGS checkpoint set is incomplete")
        if int(pc_context.apply_count) != expected_pc_applies:
            raise ValueError("M6B FBCGS total PC apply count is not 2 per iteration")
        reason_value = int(ksp.getConvergedReason())
        reason_names = []
        breakdown_names = []
        breakdown_values = set()
        for name in dir(PETSc.KSP.ConvergedReason):
            if name.startswith("_"):
                continue
            try:
                value = int(getattr(PETSc.KSP.ConvergedReason, name))
            except (TypeError, ValueError):
                continue
            if value == reason_value:
                reason_names.append(name)
            if "BREAKDOWN" in name:
                breakdown_names.append(name)
                breakdown_values.add(value)
        breakdown = bool(
            reason_value in breakdown_values
            or any("BREAKDOWN" in name for name in reason_names)
        )
        if breakdown:
            raise ValueError("M6B FBCGS breakdown reason was observed")
        return {
            "schema": M6B_W4_SCHEMA,
            "rows": rows,
            "ksp_type": "fbcgs",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "max_it": M6B_W4_KSP_ITERATIONS[-1],
            "max_it_actual": int(actual_max_it),
            "rtol": float(actual_rtol),
            "atol": float(actual_atol),
            "iterations": actual_iterations,
            "converged_reason": reason_value,
            "converged_reason_names": reason_names,
            "breakdown": breakdown,
            "breakdown_reason_names": breakdown_names,
            "samples": samples,
            "fixed_screen": True,
            "checkpoint_axis": "pc_apply_budget",
            "ksp_checkpoint_iterations": list(M6B_W4_KSP_ITERATIONS),
            "pc_apply_budgets": list(M6B_W4_PC_APPLY_BUDGETS),
            "ksp_iteration_to_pc_apply_budget": dict(M6B_W4_KSP_TO_PC_BUDGET),
            "monitor_solution_source": "direct_ksp_solution_vec",
            "buildSolution_called": False,
            "monitor_extra_pc_applies": 0,
            "pc_apply_count": int(pc_context.apply_count),
            "pc_apply_count_expected": expected_pc_applies,
            "pc_apply_count_closed": True,
            "checkpoint_operator_apply_count": operator_apply_count,
            "operator_apply_count": (
                None
                if operator_context is None
                else int(operator_context.apply_count)
            ),
            "operator_context_apply_count": (
                None
                if operator_context is None
                else operator_context.apply_count
            ),
            "sample_action_count": len(samples),
            "reported_residual_is_diagnostic_only": True,
        }
    finally:
        ksp.destroy()
        solution.destroy()
        action_work.destroy()
        residual_work.destroy()
