"""Research-only ideal capacity oracle for the frozen Task037 E2 spaces.

The implementation keeps action columns owner-local.  Each least-squares
factorization gathers only rank-local QR factors to rank zero; no global basis
matrix is assembled or replicated.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from petsc4py import PETSc
from scipy.linalg import qr, svd

from .physical_slab_two_level import SparseCoarseVector
from .static_modal_coarse_basis import OwnerLocalBasis

E2_ITERATIONS = (0, 20, 100, 200)
E2_RANK_TOLERANCE = 1.0e-12
E2_REPEAT_TOLERANCE = 1.0e-12
E2_LATE_ITERATIONS = (100, 200)
E2_CLASSIFICATION_FAIL = "M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS"
E2_CLASSIFICATION_PASS = "M120_TRIAL_SPACE_HAS_COARSE_CAPACITY"
_TINY = np.finfo(float).tiny


def _local_values(vector: PETSc.Vec) -> np.ndarray:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("capacity oracle vectors must be finite 1D arrays")
    return values


def _economic_qr(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if matrix.shape[0] == 0:
        return (
            np.zeros((0, 0), dtype=np.complex128),
            np.zeros((0, matrix.shape[1]), dtype=np.complex128),
        )
    q, r = qr(matrix, mode="economic", check_finite=True)
    return np.asarray(q, dtype=np.complex128), np.asarray(r, dtype=np.complex128)


@dataclass(frozen=True)
class DistributedLeastSquaresAudit:
    column_count: int
    effective_rank: int
    retained_condition_number: float
    singular_values: tuple[float, ...]
    rank_tolerance: float
    local_qr_method: str
    root_solve_method: str
    factorization_count: int
    normal_equations_used: bool = False


class DistributedActionLeastSquares:
    """Factor one owner-local action space and solve several residuals."""

    def __init__(
        self,
        action_columns: Sequence[PETSc.Vec],
        *,
        rank_tolerance: float = E2_RANK_TOLERANCE,
    ) -> None:
        columns = tuple(action_columns)
        if not columns:
            raise ValueError("an action space must contain at least one column")
        if rank_tolerance <= 0.0 or not np.isfinite(rank_tolerance):
            raise ValueError("rank_tolerance must be finite and positive")
        self.columns = columns
        self.comm = columns[0].getComm().tompi4py()
        self.global_rows = int(columns[0].getSize())
        self.column_count = len(columns)
        ownership = tuple(map(int, columns[0].getOwnershipRange()))
        self.ownership_range = ownership
        if any(
            int(column.getSize()) != self.global_rows
            or tuple(map(int, column.getOwnershipRange())) != ownership
            for column in columns
        ):
            raise ValueError("action columns have inconsistent PETSc layouts")
        local = np.column_stack([_local_values(column) for column in columns])
        self._local_q, local_r = _economic_qr(local)
        pieces = self.comm.gather(local_r, root=0)
        payload: dict[str, Any] | None = None
        error: str | None = None
        root_u = None
        root_singular = None
        root_vh = None
        if self.comm.rank == 0:
            try:
                stacked_r = np.vstack(pieces)
                if stacked_r.shape[0] == 0:
                    raise ValueError("action space has no owner-local rows")
                root_u, singular, root_vh = svd(
                    stacked_r,
                    full_matrices=False,
                    check_finite=True,
                )
                singular = np.asarray(singular, dtype=float)
                root_singular = singular
                scale = float(singular[0]) if singular.size else 0.0
                effective_rank = int(
                    np.count_nonzero(singular > rank_tolerance * max(scale, _TINY))
                )
                condition = (
                    float(singular[0] / singular[effective_rank - 1])
                    if effective_rank
                    else float("inf")
                )
                payload = {
                    "column_count": self.column_count,
                    "effective_rank": effective_rank,
                    "retained_condition_number": condition,
                    "singular_values": tuple(float(value) for value in singular),
                    "rank_tolerance": float(rank_tolerance),
                    "local_qr_method": "scipy.linalg.qr(economic)",
                    "root_solve_method": "scipy.linalg.svd(retained_pseudoinverse)",
                    "factorization_count": 1,
                }
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        payload, error = self.comm.bcast((payload, error), root=0)
        if error is not None or payload is None:
            raise RuntimeError(f"distributed action QR/SVD failed: {error}")
        self._root_u = root_u
        self._root_singular = root_singular
        self._root_vh = root_vh
        self.audit = DistributedLeastSquaresAudit(**payload)

    def solve(self, residual: PETSc.Vec) -> tuple[np.ndarray, PETSc.Vec]:
        if int(residual.getSize()) != self.global_rows:
            raise ValueError("residual size differs from action space")
        if tuple(map(int, residual.getOwnershipRange())) != self.ownership_range:
            raise ValueError("residual ownership differs from action space")
        local_rhs = self._local_q.conj().T @ _local_values(residual)
        pieces = self.comm.gather(local_rhs, root=0)
        coefficients: np.ndarray | None = None
        error: str | None = None
        if self.comm.rank == 0:
            try:
                rhs = (
                    np.concatenate(pieces)
                    if pieces
                    else np.empty(0, dtype=np.complex128)
                )
                rank = self.audit.effective_rank
                if rank:
                    projected = self._root_u[:, :rank].conj().T @ rhs
                    coefficients = np.asarray(
                        self._root_vh[:rank, :].conj().T
                        @ (projected / self._root_singular[:rank]),
                        dtype=np.complex128,
                    )
                else:
                    coefficients = np.zeros(
                        self.column_count,
                        dtype=np.complex128,
                    )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        coefficients, error = self.comm.bcast((coefficients, error), root=0)
        if error is not None or coefficients is None:
            raise RuntimeError(f"distributed action least-squares failed: {error}")
        corrected = residual.duplicate()
        residual.copy(corrected)
        for coefficient, column in zip(coefficients, self.columns, strict=True):
            corrected.axpy(-PETSc.ScalarType(coefficient), column)
        return coefficients, corrected


@dataclass(frozen=True)
class CapacitySpaceSolvers:
    y75: DistributedActionLeastSquares
    y_m: DistributedActionLeastSquares
    y75m: DistributedActionLeastSquares


def build_capacity_space_solvers(
    y75: Sequence[PETSc.Vec],
    y_m: Sequence[PETSc.Vec],
    *,
    rank_tolerance: float = E2_RANK_TOLERANCE,
) -> CapacitySpaceSolvers:
    y75_columns = tuple(y75)
    y_m_columns = tuple(y_m)
    return CapacitySpaceSolvers(
        y75=DistributedActionLeastSquares(
            y75_columns,
            rank_tolerance=rank_tolerance,
        ),
        y_m=DistributedActionLeastSquares(
            y_m_columns,
            rank_tolerance=rank_tolerance,
        ),
        y75m=DistributedActionLeastSquares(
            y75_columns + y_m_columns,
            rank_tolerance=rank_tolerance,
        ),
    )


def _fit(
    solver: DistributedActionLeastSquares,
    residual: PETSc.Vec,
    denominator: float,
) -> tuple[float, float, float]:
    coefficients, corrected = solver.solve(residual)
    repeated_coefficients, repeated = solver.solve(residual)
    repeat_error = float(
        np.linalg.norm(repeated_coefficients - coefficients)
        / max(float(np.linalg.norm(coefficients)), _TINY)
    )
    corrected_norm = float(corrected.norm())
    repeated_norm = float(repeated.norm())
    difference = corrected.duplicate()
    corrected.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), repeated)
    vector_repeat_error = float(difference.norm() / max(corrected_norm, _TINY))
    norm_repeat_error = abs(corrected_norm - repeated_norm) / max(
        corrected_norm,
        _TINY,
    )
    repeat_error = max(repeat_error, vector_repeat_error, norm_repeat_error)
    difference.destroy()
    repeated.destroy()
    corrected.destroy()
    return corrected_norm / max(denominator, _TINY), corrected_norm, repeat_error


def evaluate_capacity_residual(
    spaces: CapacitySpaceSolvers,
    residual: PETSc.Vec,
    b4_remainder: PETSc.Vec,
) -> dict[str, Any]:
    residual_norm = float(residual.norm())
    b4_norm = float(b4_remainder.norm())
    rho75, _, repeat75 = _fit(spaces.y75, residual, residual_norm)
    rho_m, _, repeat_m = _fit(spaces.y_m, residual, residual_norm)
    rho75m, _, repeat75m = _fit(spaces.y75m, residual, residual_norm)
    rho_bm, corrected_bm_norm, repeat_bm = _fit(
        spaces.y_m,
        b4_remainder,
        residual_norm,
    )
    return {
        "residual_norm": residual_norm,
        "rho_B": b4_norm / max(residual_norm, _TINY),
        "rho_75": rho75,
        "rho_M": rho_m,
        "rho_75M": rho75m,
        "rho_BM": rho_bm,
        "rho_hat_M_B": corrected_bm_norm / max(b4_norm, _TINY),
        "repeat_error": {
            "75D": repeat75,
            "M120": repeat_m,
            "75D+M120": repeat75m,
            "B4+M120": repeat_bm,
        },
        "improvement_M": 1.0 / max(rho_m, _TINY),
        "incremental_75_over_75M": rho75 / max(rho75m, _TINY),
    }


def materialize_sparse_columns(
    operator: PETSc.Mat,
    sparse_columns: Sequence[SparseCoarseVector],
    *,
    label: str = "Z75",
) -> OwnerLocalBasis:
    """Materialize only one owner-local 75D column set in PETSc vectors."""

    columns: list[PETSc.Vec] = []
    first, last = map(int, operator.getOwnershipRange())
    try:
        for sparse in sparse_columns:
            vector = operator.createVecRight()
            vector.set(0.0)
            if sparse.indices.size:
                if int(sparse.indices[0]) < first or int(sparse.indices[-1]) >= last:
                    vector.destroy()
                    raise ValueError("sparse coarse column is not owner-local")
                vector.setValues(sparse.indices, sparse.values)
            vector.assemble()
            columns.append(vector)
        return OwnerLocalBasis.from_vectors(
            columns,
            label=label,
            research_opt_in=True,
        )
    except Exception:
        for vector in columns:
            vector.destroy()
        raise


def _space_audit(spaces: CapacitySpaceSolvers) -> dict[str, Any]:
    return {
        "75D": asdict(spaces.y75.audit),
        "M120": asdict(spaces.y_m.audit),
        "75D+M120": asdict(spaces.y75m.audit),
    }


def qualify_e2_capacity_audit(audit: dict[str, Any]) -> dict[str, Any]:
    samples = audit.get("capacity_samples")
    samples = samples if isinstance(samples, list) else []
    by_iteration = {
        int(item["iteration"]): item
        for item in samples
        if isinstance(item, dict) and "iteration" in item
    }
    spaces = audit.get("action_spaces")
    spaces = spaces if isinstance(spaces, dict) else {}
    checks: dict[str, bool] = {
        "samples_exact": tuple(sorted(by_iteration)) == E2_ITERATIONS,
        "action_operator": audit.get("action_operator")
        == "matrix_free_condensed_F_minus_C_Hinv_D",
        "dtn_included": audit.get("dtn_included") is True,
        "normal_equations": audit.get("normal_equations_used") is False,
        "global_A_not_materialized": audit.get("global_A_materialized") is False,
        "global_F_not_materialized": audit.get("global_F_materialized") is False,
    }
    live_basis = audit.get("same_run_live_basis")
    if not isinstance(live_basis, dict):
        live_basis = {}
    z_m = live_basis.get("z_m")
    y_m = live_basis.get("y_m")
    checks["same_run_live_basis"] = (
        isinstance(z_m, dict)
        and isinstance(y_m, dict)
        and live_basis.get("same_layout") is True
        and z_m.get("global_rows") == 51192
        and y_m.get("global_rows") == 51192
        and z_m.get("column_count") == 240
        and y_m.get("column_count") == 240
        and z_m.get("owner_local") is True
        and y_m.get("owner_local") is True
    )
    for name in ("75D", "M120", "75D+M120"):
        summary = spaces.get(name, {})
        singular = summary.get("singular_values", ())
        rank = summary.get("effective_rank")
        condition = summary.get("retained_condition_number")
        checks[f"{name}_rank"] = isinstance(rank, int) and rank > 0
        checks[f"{name}_condition"] = isinstance(
            condition, (int, float)
        ) and bool(np.isfinite(condition))
        checks[f"{name}_singular_values"] = bool(singular) and all(
            np.isfinite(float(value)) for value in singular
        )
        checks[f"{name}_factorization_once"] = (
            summary.get("factorization_count") == 1
            and summary.get("root_solve_method")
            == "scipy.linalg.svd(retained_pseudoinverse)"
        )
    for iteration, item in by_iteration.items():
        for field in (
            "rho_75",
            "rho_M",
            "rho_75M",
            "rho_BM",
            "rho_hat_M_B",
        ):
            checks[f"finite_{iteration}_{field}"] = bool(
                isinstance(item.get(field), (int, float))
                and np.isfinite(float(item[field]))
            )
        repeats = item.get("repeat_error", {})
        checks[f"repeat_{iteration}"] = all(
            isinstance(repeats.get(name), (int, float))
            and np.isfinite(float(repeats[name]))
            and float(repeats[name]) <= E2_REPEAT_TOLERANCE
            for name in ("75D", "M120", "75D+M120", "B4+M120")
        )
    implementation_checks = dict(checks)
    implementation_checks["75D_rank_exact"] = (
        spaces.get("75D", {}).get("effective_rank") == 75
    )
    implementation_checks["M120_rank_minimum"] = (
        isinstance(spaces.get("M120", {}).get("effective_rank"), int)
        and spaces["M120"]["effective_rank"] >= 180
    )
    implementation_checks["combined_rank_dominates_components"] = isinstance(
        spaces.get("75D+M120", {}).get("effective_rank"), int
    ) and spaces["75D+M120"]["effective_rank"] >= max(
        int(spaces.get("75D", {}).get("effective_rank", -1)),
        int(spaces.get("M120", {}).get("effective_rank", -1)),
    )
    implementation_failures = [
        name for name, passed in implementation_checks.items() if not passed
    ]
    capacity_checks: dict[str, bool] = {}
    for iteration in E2_LATE_ITERATIONS:
        item = by_iteration.get(iteration, {})
        capacity_checks[f"late_{iteration}_modal_improvement"] = (
            float(item.get("improvement_M", -np.inf)) >= 1.5
        )
        capacity_checks[f"late_{iteration}_b4_remainder"] = (
            float(item.get("rho_hat_M_B", np.inf)) <= 0.67
        )
        capacity_checks[f"late_{iteration}_incremental"] = (
            float(item.get("incremental_75_over_75M", -np.inf)) >= 1.20
        )
    capacity_failures = [name for name, passed in capacity_checks.items() if not passed]
    if implementation_failures:
        classification = "M120_MODAL_CAPACITY_IMPLEMENTATION_FAILED"
        status = "implementation_failure"
    elif capacity_failures:
        classification = E2_CLASSIFICATION_FAIL
        status = "capacity_negative"
    else:
        classification = E2_CLASSIFICATION_PASS
        status = "capacity_pass"
    failures = implementation_failures + capacity_failures
    return {
        "pass": not failures,
        "status": status,
        "checks": implementation_checks,
        "capacity_checks": capacity_checks,
        "implementation_failures": implementation_failures,
        "capacity_failures": capacity_failures,
        "failures": failures,
        "classification": classification,
    }


def run_e2_capacity_oracle(
    request: Any,
    z_m: OwnerLocalBasis,
    y_m: OwnerLocalBasis,
    e1_operator: PETSc.Mat,
    *,
    run_dir: str | Path,
    source_sha: str,
    research_opt_in: bool = False,
) -> dict[str, Any]:
    """Run one same-request B4 solve and evaluate the five capacity spaces."""

    if research_opt_in is not True:
        raise ValueError("E2 capacity oracle is research-only")
    comm = e1_operator.getComm().tompi4py()
    residuals: dict[int, PETSc.Vec] = {}
    rhs_norms: dict[int, float] = {}
    holder: dict[str, Any] = {}

    def capture(iteration: int, residual: PETSc.Vec, rhs_norm: float) -> None:
        iteration = int(iteration)
        if iteration not in E2_ITERATIONS or iteration in residuals:
            return
        copied = residual.duplicate()
        residual.copy(copied)
        residuals[iteration] = copied
        rhs_norms[iteration] = float(rhs_norm)

    def capacity_observer(
        core_operator: PETSc.Mat,
        sparse_basis: tuple[SparseCoarseVector, ...],
        b4_coarse: Any,
    ) -> None:
        if tuple(sorted(residuals)) != E2_ITERATIONS:
            raise RuntimeError("E2 B4 residual vector samples are incomplete")
        z75 = materialize_sparse_columns(core_operator, sparse_basis)
        y75 = None
        z_b = None
        a_z_b = None
        r_b = None
        try:
            y75 = z75.apply(core_operator, label="Y75", research_opt_in=True)
            spaces = build_capacity_space_solvers(y75.columns, y_m.columns)
            records = []
            for iteration in E2_ITERATIONS:
                residual = residuals[iteration]
                z_b = core_operator.createVecRight()
                b4_coarse.apply(None, residual, z_b)
                a_z_b = core_operator.createVecLeft()
                core_operator.mult(z_b, a_z_b)
                r_b = residual.duplicate()
                residual.copy(r_b)
                r_b.axpy(PETSc.ScalarType(-1.0), a_z_b)
                record = evaluate_capacity_residual(spaces, residual, r_b)
                record["iteration"] = iteration
                record["rhs_norm"] = rhs_norms[iteration]
                record["relative_true_residual"] = record["residual_norm"] / max(
                    rhs_norms[iteration], _TINY
                )
                records.append(record)
                r_b.destroy()
                r_b = None
                a_z_b.destroy()
                a_z_b = None
                z_b.destroy()
                z_b = None
            holder["capacity"] = {
                "schema_version": "task037.e2.capacity-oracle.v1",
                "source_sha": source_sha,
                "research_only": True,
                "ordinary_default_changed": False,
                "action_operator": "matrix_free_condensed_F_minus_C_Hinv_D",
                "dtn_included": True,
                "normal_equations_used": False,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "capacity_samples": records,
                "action_spaces": _space_audit(spaces),
                "same_run_live_basis": {
                    "z_m": {
                        "global_rows": int(z_m.global_rows),
                        "column_count": int(z_m.column_count),
                        "ownership": list(z_m.ownership_range),
                        "owner_local": True,
                    },
                    "y_m": {
                        "global_rows": int(y_m.global_rows),
                        "column_count": int(y_m.column_count),
                        "ownership": list(y_m.ownership_range),
                        "owner_local": True,
                    },
                    "same_layout": (
                        z_m.global_rows == y_m.global_rows
                        and z_m.ownership_range == y_m.ownership_range
                    ),
                },
            }
        finally:
            if r_b is not None:
                r_b.destroy()
            if a_z_b is not None:
                a_z_b.destroy()
            if z_b is not None:
                z_b.destroy()
            if y75 is not None:
                y75.destroy()
            z75.destroy()

    from .static_condensed_iterative import (
        solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres,
    )

    nested_snapshot = None
    try:
        nested_snapshot, core_audit = (
            solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres(
                request,
                screen_iterations=200,
                local_krylov_steps=4,
                true_residual_vector_observer=capture,
                task037_e2_capacity_live_observer=capacity_observer,
            )
        )
        audit = holder["capacity"]
        audit["core"] = {
            "solver_profile": core_audit.get("solver_profile"),
            "candidate": core_audit.get("candidate"),
            "global_A_materialized": core_audit.get("global_A_materialized"),
            "global_F_materialized": core_audit.get("global_F_materialized"),
            "no_global_factor_inventory": core_audit.get("no_global_factor_inventory"),
            "final": core_audit.get("final"),
        }
        audit["solver_convergence_gate"] = {
            "pass": int(nested_snapshot.converged_reason) > 0,
            "converged_reason": int(nested_snapshot.converged_reason),
            "iterations": int(nested_snapshot.iterations),
            "independent_of_capacity_gate": True,
        }
        result = qualify_e2_capacity_audit(audit)
        audit["capacity_gate_pass"] = bool(result["pass"])
        audit["classification"] = result["classification"]
        audit["checker"] = result
        if comm.rank == 0:
            path = Path(run_dir) / "task037_e2_modal_capacity_audit.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        comm.barrier()
        return audit
    finally:
        if nested_snapshot is not None and nested_snapshot.x is not None:
            nested_snapshot.x.destroy()
        for vector in residuals.values():
            vector.destroy()


__all__ = (
    "E2_CLASSIFICATION_FAIL",
    "E2_CLASSIFICATION_PASS",
    "E2_ITERATIONS",
    "CapacitySpaceSolvers",
    "DistributedActionLeastSquares",
    "build_capacity_space_solvers",
    "evaluate_capacity_residual",
    "materialize_sparse_columns",
    "qualify_e2_capacity_audit",
    "run_e2_capacity_oracle",
)
