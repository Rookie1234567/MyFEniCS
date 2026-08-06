from __future__ import annotations

import json

import numpy as np
import pytest
import scipy.linalg
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
)
from src.solvers.static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from src.solvers.static_local_schur_action import create_static_local_schur_action
from src.solvers.static_p4_capacity_oracle import (
    build_p4_capacity_oracle,
    local_transfer_matrix,
)
from src.solvers.static_trace_auxiliary import (
    build_owner_local_trace_transfer,
    build_p2_to_p6_active_trace_transfer,
)
from src.test.test_234_task037_p2_trace_transfer import _constraint_map
from src.test.test_235_task037_p2_galerkin_auxiliary import _retained_p6_fixture
from src.test.test_236_task037_p2_auxiliary_pc import _assembly_time_fixture
from src.test.test_241_task037_candidate_d_local_p2 import _shifted_diagonal
from src.test.test_246_task037_p4_capacity_oracle import (
    _adjoint_relative,
    _relative,
    _spaces,
)


def _least_squares(matrix: np.ndarray, rhs: np.ndarray):
    matrix = np.asarray(matrix, dtype=PETSc.ScalarType)
    rhs = np.asarray(rhs, dtype=PETSc.ScalarType)
    assert np.all(np.isfinite(matrix))
    assert np.all(np.isfinite(rhs))
    solution, _, rank, singular_values = scipy.linalg.lstsq(
        matrix, rhs, lapack_driver="gelsd"
    )
    repeated, _, repeated_rank, _ = scipy.linalg.lstsq(
        matrix, rhs, lapack_driver="gelsd"
    )
    residual = rhs - matrix @ solution
    scale = max(float(np.linalg.norm(rhs)), 1.0e-30)
    raw_ls_residual = float(np.linalg.norm(residual))
    normalized_ls_residual = raw_ls_residual / scale
    raw_orthogonality_norm = float(np.linalg.norm(matrix.conj().T @ residual))
    normalized_orthogonality = raw_orthogonality_norm / max(
        float(np.linalg.norm(matrix) * np.linalg.norm(residual)), 1.0e-30
    )
    repeat_error = float(np.linalg.norm(solution - repeated)) / max(
        float(np.linalg.norm(solution)), 1.0e-30
    )
    nonzero = singular_values[: int(rank)]
    assert np.all(np.isfinite(solution))
    assert np.all(np.isfinite(repeated))
    assert np.all(np.isfinite(singular_values))
    assert np.all(np.isfinite(residual))
    assert int(rank) > 0
    assert int(repeated_rank) > 0
    assert nonzero.size > 0
    condition = float(nonzero[0] / nonzero[-1])
    numeric_scalars = np.asarray(
        [
            condition,
            raw_ls_residual,
            normalized_ls_residual,
            raw_orthogonality_norm,
            normalized_orthogonality,
            repeat_error,
        ],
        dtype=float,
    )
    assert np.all(np.isfinite(numeric_scalars))
    report = {
        "rank": int(rank),
        "repeat_rank": int(repeated_rank),
        "condition": condition,
        "singular_spectrum": {
            "count": int(singular_values.size),
            "max": float(singular_values[0]) if singular_values.size else 0.0,
            "min_nonzero": float(nonzero[-1]) if nonzero.size else None,
        },
        "ls_residual": raw_ls_residual,
        "normalized_ls_residual": normalized_ls_residual,
        "raw_orthogonality_norm": raw_orthogonality_norm,
        "normalized_orthogonality": normalized_orthogonality,
        "repeat_error": repeat_error,
    }
    assert report["repeat_rank"] == report["rank"]
    assert report["repeat_error"] <= 1.0e-12
    return solution, report


def _action_matrix(pc, slab: int, basis: np.ndarray) -> np.ndarray:
    return np.column_stack(
        [
            pc.restricted_action(slab, basis[:, column])
            for column in range(basis.shape[1])
        ]
    )


def _b4_basis(pc, slab: int, rhs: np.ndarray):
    """Mirror _fixed_step_gmres Arnoldi order without changing the solver."""

    assert pc._p2_factors is None
    assert pc.rank == int(pc.plan.slab_owners[slab])
    rhs = np.asarray(rhs, dtype=PETSc.ScalarType)
    beta = float(np.linalg.norm(rhs))
    tiny = np.finfo(float).tiny
    q_vectors = [rhs / beta if beta > tiny else np.zeros_like(rhs)]
    steps = pc._local_krylov_steps
    hessenberg = np.zeros((steps + 1, steps), dtype=PETSc.ScalarType)
    active = beta > tiny
    for step in range(steps):
        q = q_vectors[step] if active else np.zeros_like(rhs)
        w = pc._restricted_action(slab, q)
        if not active:
            if step + 1 < steps:
                q_vectors.append(np.zeros_like(rhs))
            continue
        for previous, q_previous in enumerate(q_vectors[: step + 1]):
            coefficient = np.vdot(q_previous, w) if q.size else 0.0
            hessenberg[previous, step] = coefficient
            w = w - coefficient * q_previous
        next_norm = float(np.linalg.norm(w))
        hessenberg[step + 1, step] = next_norm
        if next_norm <= tiny:
            active = False
            if step + 1 < steps:
                q_vectors.append(np.zeros_like(rhs))
        elif step + 1 < steps:
            q_vectors.append(w / next_norm)
    basis = np.column_stack(q_vectors[:steps])
    g = np.zeros(steps + 1, dtype=PETSc.ScalarType)
    g[0] = beta
    return basis, hessenberg, g


def _rho(rhs: np.ndarray, action, correction: np.ndarray) -> float:
    residual = rhs - action(correction)
    return float(np.linalg.norm(residual)) / max(float(np.linalg.norm(rhs)), 1.0e-30)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="F0b is serial-only")
def test_f0b_decisive_capacity_oracle():
    comm = MPI.COMM_WORLD
    mesh_3d, (V2, V6), (C2, C6) = _spaces(comm, nx=1, ny=1, nz=1)
    V4 = fem.functionspace(
        mesh_3d,
        element("N1curl", mesh_3d.basix_cell(), 4, dtype=default_real_type),
    )
    C4 = _constraint_map(V4)
    fine_condensed, _schurs = _retained_p6_fixture(V6, C6)
    fine_condensed = _assembly_time_fixture(C6, fine_condensed, comm)
    fine_action, fine_action_context = create_static_local_schur_action(fine_condensed)
    diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)
    shifted = _shifted_diagonal(diagonal, diagonal_audit["global_diagonal_max_abs"])
    p24_transfer = build_owner_local_trace_transfer(
        V2, V4, C2, C4, coarse_degree=2, fine_degree=4
    )
    p46_transfer = build_owner_local_trace_transfer(
        V4, V6, C4, C6, coarse_degree=4, fine_degree=6
    )
    p26_transfer = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    plan = build_owner_local_slab_plan(
        fine_condensed,
        mesh_3d,
        domain_z=(0.0, 1.0),
        num_slabs=2,
        overlap_fraction=0.125,
    )
    b4 = FactorFreeLocalSlabKrylovPc(fine_action, plan, shifted, local_krylov_steps=4)
    oracle = None
    audit = None
    scientific_failure = False
    try:
        slab = 0
        p6_rows = np.asarray(plan.owner_rows[slab], dtype=PETSc.IntType)
        combined_diagonal = diagonal.getValues(p6_rows) + shifted.getValues(p6_rows)
        oracle = build_p4_capacity_oracle(
            b4, slab, p46_transfer, p24_transfer, combined_diagonal
        )
        assert oracle.audit["p6_slab_matrix_materialized"] is False
        assert oracle.audit["p6_slab_matrix_count"] == 0
        assert oracle.audit["p6_slab_matrix_nnz"] == 0
        assert oracle.audit["p6_factor_count"] == 0
        assert oracle.audit["p6_factor_nnz"] == 0
        assert oracle.audit["p6_slab_rows"] == 432
        assert oracle.audit["p4_trace_factor_rows"] == 192
        assert oracle.audit["p2_trace_factor_rows"] == 48

        p26_columns, p26_dense = local_transfer_matrix(p26_transfer, p6_rows)
        assert np.array_equal(p26_columns, oracle.p2_row_ids)
        nested_error = _relative(p26_dense, oracle.p46 @ oracle.p24)
        p24_adjoint_error = _adjoint_relative(p24_transfer, V2, V4, C2, C4)
        p46_adjoint_error = _adjoint_relative(p46_transfer, V4, V6, C4, C6)
        y4 = _action_matrix(b4, slab, oracle.p46)
        y4_probe = np.sin(0.29 * np.arange(oracle.p46.shape[1])) + 1j * np.cos(
            0.41 * np.arange(oracle.p46.shape[1])
        )
        y4_action_error = _relative(y4 @ y4_probe, oracle.action(oracle.p46 @ y4_probe))
        assert nested_error <= 1.0e-11
        assert p24_adjoint_error <= 1.0e-11
        assert p46_adjoint_error <= 1.0e-11
        assert y4_action_error <= 1.0e-11
        assert p24_transfer.audit["coarse_degree"] == 2
        assert p24_transfer.audit["fine_degree"] == 4
        assert p46_transfer.audit["coarse_degree"] == 4
        assert p46_transfer.audit["fine_degree"] == 6
        assert p24_transfer.audit["trace_interior_dependency_max"] <= 1.0e-12
        assert p46_transfer.audit["trace_interior_dependency_max"] <= 1.0e-12

        frozen_b4 = {
            "low": 0.24599945418880295,
            "high": 0.24651896436171644,
            "mixed": 0.24612971921817314,
        }
        frozen_d0 = {
            "low": 0.2540230551088513,
            "high": 0.26531876351572775,
            "mixed": 0.2715867504171219,
        }
        p26_range = np.linalg.qr(p26_dense, mode="reduced")[0]
        p2_seed = np.sin(0.13 * np.arange(p26_dense.shape[1])) + 1j * np.cos(
            0.17 * np.arange(p26_dense.shape[1])
        )
        low = p26_dense @ p2_seed
        low /= np.linalg.norm(low)
        p6_seed = np.cos(0.07 * np.arange(p26_dense.shape[0])) + 1j * np.sin(
            0.11 * np.arange(p26_dense.shape[0])
        )
        high = p6_seed - p26_range @ (p26_range.conj().T @ p6_seed)
        assert np.linalg.norm(high) > 1.0e-12
        high /= np.linalg.norm(high)
        mixed = low + high
        mixed /= np.linalg.norm(mixed)
        source_metrics = {}
        for name, rhs in {"low": low, "high": high, "mixed": mixed}.items():
            action = oracle.action

            z_diagonal = rhs / combined_diagonal
            y_galerkin = oracle.solve_p4(oracle.p46.conj().T @ rhs)
            y_galerkin_repeat = oracle.solve_p4(oracle.p46.conj().T @ rhs)
            z_galerkin = oracle.p46 @ y_galerkin
            r_after_diagonal = rhs - action(z_diagonal)
            y_diag_galerkin = oracle.solve_p4(oracle.p46.conj().T @ r_after_diagonal)
            z_diag_galerkin = z_diagonal + oracle.p46 @ y_diag_galerkin

            v_b4, h_b4, g_b4 = _b4_basis(b4, slab, rhs)
            b4_coefficients, b4_report = _least_squares(h_b4, g_b4)
            z_b4_basis = v_b4 @ b4_coefficients
            rho_b4_basis = _rho(rhs, action, z_b4_basis)
            z_b4_actual, _happy_breakdown = b4._fixed_step_gmres(slab, rhs)
            rho_b4_actual = _rho(rhs, action, z_b4_actual)
            assert abs(rho_b4_basis - rho_b4_actual) <= 1.0e-12
            assert abs(rho_b4_actual - frozen_b4[name]) <= 1.0e-12
            assert np.all(np.isfinite(z_b4_actual))

            p4_coefficients, p4_report = _least_squares(y4, rhs)
            z_p4_minres = oracle.p46 @ p4_coefficients
            z_augmented_basis = np.column_stack((v_b4, oracle.p46))
            y_augmented = np.column_stack((_action_matrix(b4, slab, v_b4), y4))
            augmented_coefficients, augmented_report = _least_squares(y_augmented, rhs)
            z_augmented = z_augmented_basis @ augmented_coefficients
            rho_diagonal = _rho(rhs, action, z_diagonal)
            rho_galerkin = _rho(rhs, action, z_galerkin)
            rho_diagonal_to_p4_galerkin = _rho(rhs, action, z_diag_galerkin)
            rho_p4_minres = _rho(rhs, action, z_p4_minres)
            rho_augmented = _rho(rhs, action, z_augmented)
            p4_minres_improvement = rho_b4_actual / rho_p4_minres
            augmented_minres_improvement = rho_b4_actual / rho_augmented
            for value in (
                rho_b4_actual,
                rho_diagonal,
                rho_galerkin,
                rho_diagonal_to_p4_galerkin,
                rho_p4_minres,
                rho_augmented,
                p4_minres_improvement,
                augmented_minres_improvement,
            ):
                assert np.isfinite(value)
            assert np.all(np.isfinite(y_galerkin))
            assert np.all(np.isfinite(y_galerkin_repeat))
            assert np.linalg.norm(y_galerkin - y_galerkin_repeat) <= 1.0e-12
            source_metrics[name] = {
                "rho_B4": rho_b4_actual,
                "rho_diagonal": rho_diagonal,
                "rho_p4_galerkin": rho_galerkin,
                "rho_diagonal_to_p4_galerkin": rho_diagonal_to_p4_galerkin,
                "rho_p4_minres": rho_p4_minres,
                "rho_augmented": rho_augmented,
                "p4_minres_improvement": p4_minres_improvement,
                "augmented_minres_improvement": augmented_minres_improvement,
                "rho_D0_frozen": frozen_d0[name],
                "b4_basis_alignment": {
                    "rho_basis": rho_b4_basis,
                    "rho_actual": rho_b4_actual,
                    "report": b4_report,
                },
                "p4_minres_space": p4_report,
                "augmented_minres_space": augmented_report,
                "p4_galerkin_repeat_error": float(
                    np.linalg.norm(y_galerkin - y_galerkin_repeat)
                ),
            }

        audit = {
            "fixture": {
                "nx_ny_nz": [1, 1, 1],
                "slabs": 2,
                "slab": 0,
                "overlap": 0.125,
                "degrees": [2, 4, 6],
                "local_steps": 4,
            },
            "implementation_gates": {
                "nested_p26_vs_p46_p24": nested_error,
                "p24_adjoint": p24_adjoint_error,
                "p46_adjoint": p46_adjoint_error,
                "y4_action": y4_action_error,
                "all_solutions_finite": True,
                "p6_matrix_factor_nnz": [0, 0, 0],
                "ordinary_defaults_changed": False,
            },
            "inventory": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in oracle.audit.items()
            },
            "transfer_inventory": {
                "P24": {
                    "coarse_degree": int(p24_transfer.audit["coarse_degree"]),
                    "fine_degree": int(p24_transfer.audit["fine_degree"]),
                    "nnz": int(p24_transfer.audit["global_stencil_nnz"]),
                    "trace_interior_dependency_max": float(
                        p24_transfer.audit["trace_interior_dependency_max"]
                    ),
                },
                "P46": {
                    "coarse_degree": int(p46_transfer.audit["coarse_degree"]),
                    "fine_degree": int(p46_transfer.audit["fine_degree"]),
                    "nnz": int(p46_transfer.audit["global_stencil_nnz"]),
                    "trace_interior_dependency_max": float(
                        p46_transfer.audit["trace_interior_dependency_max"]
                    ),
                },
                "rows": {
                    "p6": 432,
                    "p4": 192,
                    "p2": 48,
                },
            },
            "sources": source_metrics,
        }
        high = source_metrics["high"]
        mixed = source_metrics["mixed"]
        high_improvement = high["augmented_minres_improvement"]
        mixed_improvement = mixed["augmented_minres_improvement"]
        scientific_failure = (
            high_improvement < 1.5
            or high["rho_augmented"] >= 0.15
            or mixed_improvement < 1.5
            or mixed["rho_augmented"] >= 0.15
        )
        audit["science_gate"] = {
            "improvement_threshold": 1.5,
            "augmented_rho_threshold": 0.15,
            "high_augmented_improvement": high_improvement,
            "mixed_augmented_improvement": mixed_improvement,
            "high_augmented_rho": high["rho_augmented"],
            "mixed_augmented_rho": mixed["rho_augmented"],
            "status": "family_closed" if scientific_failure else "capacity_pass",
            "classification": (
                "P6_P4_P2_FAMILY_CLOSED_ON_FROZEN_CAPACITY_ORACLE"
                if scientific_failure
                else "P4_TRIAL_SPACE_HAS_CAPACITY_CURRENT_GALERKIN_COMBINATION_FAILED"
            ),
        }
    finally:
        if oracle is not None:
            oracle.destroy()
        b4.destroy()
        shifted.destroy()
        diagonal.destroy()
        p24_transfer.destroy()
        p46_transfer.destroy()
        p26_transfer.destroy()
        fine_action_context.destroy(fine_action)
        fine_action.destroy()
        fine_condensed.destroy()

    print("F0B_DECISIVE_CAPACITY_AUDIT", json.dumps(audit, sort_keys=True))
    if scientific_failure:
        pytest.fail("P6_P4_P2_FAMILY_CLOSED_ON_FROZEN_CAPACITY_ORACLE")
    print("P4_TRIAL_SPACE_HAS_CAPACITY_CURRENT_GALERKIN_COMBINATION_FAILED")
