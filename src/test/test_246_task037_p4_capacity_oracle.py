from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
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
from src.test.test_234_task037_p2_trace_transfer import (
    _active_vector,
    _active_from_field,
    _constraint_map,
    _field_from_active,
    _fixed_target_fixture,
    _probe,
    _spaces,
)
from src.test.test_235_task037_p2_galerkin_auxiliary import _retained_p6_fixture
from src.test.test_236_task037_p2_auxiliary_pc import _assembly_time_fixture
from src.test.test_241_task037_candidate_d_local_p2 import _shifted_diagonal


def _relative(left, right):
    return float(np.linalg.norm(left - right)) / max(
        float(np.linalg.norm(right)), 1.0e-30
    )


def _adjoint_relative(
    transfer, coarse_space, fine_space, coarse_constraints, fine_constraints
):
    coarse = _active_vector(coarse_space, coarse_constraints)
    fine = _active_vector(fine_space, fine_constraints)
    image = _active_vector(fine_space, fine_constraints)
    adjoint = _active_vector(coarse_space, coarse_constraints)
    _probe(coarse, 246)
    _probe(fine, 247)
    transfer.apply(coarse, image)
    transfer.apply_adjoint(fine, adjoint)
    lhs = image.dot(fine)
    rhs = coarse.dot(adjoint)
    coarse.destroy()
    fine.destroy()
    image.destroy()
    adjoint.destroy()
    return float(abs(lhs - rhs)) / max(float(abs(lhs)), 1.0)


def _rho(pc, slab, rhs):
    correction, _happy_breakdown = pc._fixed_step_gmres(slab, rhs)
    residual = rhs - pc.restricted_action(slab, correction)
    return float(np.linalg.norm(residual)) / max(float(np.linalg.norm(rhs)), 1.0e-30)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="F0 is serial-only")
def test_f0_p4_capacity_oracle_and_d0_comparison():
    comm = MPI.COMM_WORLD
    mesh_3d, (V2, V6), (C2, C6) = _spaces(comm, nx=1, ny=1, nz=1)
    V4 = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            4,
            dtype=default_real_type,
        ),
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
    b4 = FactorFreeLocalSlabKrylovPc(
        fine_action,
        plan,
        shifted,
        local_krylov_steps=4,
    )
    slab = 0
    p6_rows = np.asarray(plan.owner_rows[slab], dtype=PETSc.IntType)
    combined_diagonal = diagonal.getValues(p6_rows) + shifted.getValues(p6_rows)
    oracle = build_p4_capacity_oracle(
        b4,
        slab,
        p46_transfer,
        p24_transfer,
        combined_diagonal,
    )
    assert oracle.audit["p6_slab_matrix_materialized"] is False
    assert oracle.audit["p6_slab_matrix_count"] == 0
    assert oracle.audit["p6_slab_matrix_nnz"] == 0
    assert oracle.audit["p6_factor_count"] == 0
    assert oracle.audit["p6_factor_nnz"] == 0
    assert oracle.audit["p4_trace_factor_rows"] == oracle.p46.shape[1]
    assert oracle.audit["p2_trace_factor_rows"] == oracle.p24.shape[1]
    assert oracle.audit["p4_matrix_nnz"] > 0
    assert oracle.audit["p4_factor_nnz"] > 0
    assert oracle.audit["p4_lu_payload_bytes"] > 0
    assert V2.element.space_dimension == 54
    assert V4.element.space_dimension == 300
    assert V6.element.space_dimension == 882
    assert oracle.audit["p6_slab_rows"] == 432
    assert oracle.audit["p4_trace_factor_rows"] == 192
    assert oracle.audit["p2_trace_factor_rows"] == 48
    assert p24_transfer.audit["coarse_degree"] == 2
    assert p24_transfer.audit["fine_degree"] == 4
    assert p46_transfer.audit["coarse_degree"] == 4
    assert p46_transfer.audit["fine_degree"] == 6
    assert p24_transfer.audit["trace_interior_dependency_max"] <= 1.0e-12
    assert p46_transfer.audit["trace_interior_dependency_max"] <= 1.0e-12

    x4 = np.sin(0.17 * np.arange(oracle.p46.shape[1])) + 1j * np.cos(
        0.23 * np.arange(oracle.p46.shape[1])
    )
    projected4 = oracle.p46.conj().T @ oracle.action(oracle.p46 @ x4)
    projected4_error = _relative(projected4, oracle.a4 @ x4)
    x2 = np.sin(0.19 * np.arange(oracle.p24.shape[1])) + 1j * np.cos(
        0.29 * np.arange(oracle.p24.shape[1])
    )
    p4_image = oracle.p24 @ x2
    p6_image = oracle.p46 @ p4_image
    projected2 = oracle.p24.conj().T @ (oracle.p46.conj().T @ oracle.action(p6_image))
    projected2_error = _relative(projected2, oracle.a2 @ x2)
    assert projected4_error <= 1.0e-11
    assert projected2_error <= 1.0e-11
    p46_adjoint_error = _adjoint_relative(p46_transfer, V4, V6, C4, C6)
    p24_adjoint_error = _adjoint_relative(p24_transfer, V2, V4, C2, C4)
    assert p46_adjoint_error <= 1.0e-11
    assert p24_adjoint_error <= 1.0e-11

    p4_rhs = np.sin(0.31 * np.arange(oracle.p46.shape[1])) + 1j * np.cos(
        0.37 * np.arange(oracle.p46.shape[1])
    )
    first_p4 = oracle.solve_p4(p4_rhs)
    second_p4 = oracle.solve_p4(p4_rhs)
    p4_repeat_error = float(np.max(np.abs(first_p4 - second_p4), initial=0.0))
    assert np.all(np.isfinite(first_p4))
    assert np.all(np.isfinite(second_p4))
    assert p4_repeat_error <= 1.0e-12

    p26_columns, p26_dense = local_transfer_matrix(p26_transfer, p6_rows)
    assert np.array_equal(p26_columns, oracle.p2_row_ids)
    q_range = np.linalg.qr(p26_dense, mode="reduced")[0]
    p2_seed = np.sin(0.13 * np.arange(p26_dense.shape[1])) + 1j * np.cos(
        0.17 * np.arange(p26_dense.shape[1])
    )
    low = p26_dense @ p2_seed
    low /= np.linalg.norm(low)
    p6_seed = np.cos(0.07 * np.arange(p26_dense.shape[0])) + 1j * np.sin(
        0.11 * np.arange(p26_dense.shape[0])
    )
    high = p6_seed - q_range @ (q_range.conj().T @ p6_seed)
    assert np.linalg.norm(high) > 1.0e-12
    high /= np.linalg.norm(high)
    high_complement_absolute = float(np.linalg.norm(p26_dense.conj().T @ high))
    assert high_complement_absolute <= 1.0e-11
    mixed = low + high
    mixed /= np.linalg.norm(mixed)
    metrics = {}
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
    for name, source in {"low": low, "high": high, "mixed": mixed}.items():
        rho_b4 = _rho(b4, slab, source)
        rho_f = float(
            np.linalg.norm(source - oracle.action(oracle.correction(source)))
        ) / max(float(np.linalg.norm(source)), 1.0e-30)
        assert _relative(np.asarray([rho_b4]), np.asarray([frozen_b4[name]])) <= 1.0e-12
        metrics[name] = {
            "rho_B4": rho_b4,
            "rho_F": rho_f,
            "rho_D0_frozen": frozen_d0[name],
            "improvement": rho_b4 / rho_f,
        }
        assert np.isfinite(rho_b4) and np.isfinite(rho_f)

    print(
        "F0_P4_CAPACITY_AUDIT",
        {
            "transfer46_adjoint_error": p46_adjoint_error,
            "transfer24_adjoint_error": p24_adjoint_error,
            "projected4_error": projected4_error,
            "projected2_error": projected2_error,
            "high_complement_absolute": high_complement_absolute,
            "p4_repeat_error": p4_repeat_error,
            "metrics": metrics,
            "inventory": oracle.audit,
            "frozen_D0_inventory": {"factor_count": 2, "factor_nnz": 4608},
        },
    )
    gate_failure = (
        metrics["high"]["improvement"] < 1.5 or metrics["mixed"]["improvement"] < 1.5
    )
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
    if gate_failure:
        pytest.fail(
            "P4_INTERMEDIATE_SPACE_NOT_EFFECTIVE: "
            f"high improvement={metrics['high']['improvement']:.16g}, "
            f"mixed improvement={metrics['mixed']['improvement']:.16g}"
        )


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="F0 is serial-only")
def test_f0_degree_pairs_preserve_floquet_orientation_identity():
    cfg, mesh_data, V2 = _fixed_target_fixture(2, h_nm=50.0)
    cfg = replace(cfg, incident_phi_deg=37.0)
    V4 = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            4,
            dtype=default_real_type,
        ),
    )
    V6 = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    C2_data = build_double_floquet_mpc(V2, mesh_data, cfg)
    C4_data = build_double_floquet_mpc(V4, mesh_data, replace(cfg, nedelec_degree=4))
    C6_data = build_double_floquet_mpc(V6, mesh_data, replace(cfg, nedelec_degree=6))
    C2 = _constraint_map(V2, C2_data.mpc)
    C4 = _constraint_map(V4, C4_data.mpc)
    C6 = _constraint_map(V6, C6_data.mpc)
    p24 = build_owner_local_trace_transfer(
        V2, V4, C2, C4, coarse_degree=2, fine_degree=4
    )
    p46 = build_owner_local_trace_transfer(
        V4, V6, C4, C6, coarse_degree=4, fine_degree=6
    )
    p26 = build_p2_to_p6_active_trace_transfer(V2, V6, C2, C6)
    q2 = _active_vector(V2, C2)
    q4 = _active_vector(V4, C4)
    q6_composed = _active_vector(V6, C6)
    q6_direct = _active_vector(V6, C6)
    _probe(q2, 248)
    p24.apply(q2, q4)
    q2_field = _field_from_active(V2, C2, q2)
    p4_interpolated = fem.Function(V4)
    p4_interpolated.interpolate(q2_field)
    p4_interpolated.x.scatter_forward()
    q4_reference = _active_from_field(V4, C4, p4_interpolated)
    p24_error = _relative(
        q4.getArray(readonly=True), q4_reference.getArray(readonly=True)
    )
    assert p24_error <= 1.0e-11
    p46.apply(q4, q6_composed)
    p26.apply(q2, q6_direct)
    composed = q6_composed.getArray(readonly=True)
    direct = q6_direct.getArray(readonly=True)
    composition_error = _relative(composed, direct)
    assert composition_error <= 1.0e-11
    q4_probe = _active_vector(V4, C4)
    q6_transfer = _active_vector(V6, C6)
    _probe(q4_probe, 249)
    p46.apply(q4_probe, q6_transfer)
    q4_probe_field = _field_from_active(V4, C4, q4_probe)
    p6_interpolated = fem.Function(V6)
    p6_interpolated.interpolate(q4_probe_field)
    p6_interpolated.x.scatter_forward()
    q6_reference = _active_from_field(V6, C6, p6_interpolated)
    p46_error = _relative(
        q6_transfer.getArray(readonly=True), q6_reference.getArray(readonly=True)
    )
    assert p46_error <= 1.0e-11
    assert p24.audit["cell_info_nonzero_count"] > 0
    assert p46.audit["cell_info_nonzero_count"] > 0
    assert p26.audit["cell_info_nonzero_count"] > 0
    assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_y) - 1.0) > 1.0e-8
    assert abs(complex(cfg.floquet_phase_x * cfg.floquet_phase_y) - 1.0) > 1.0e-8
    p24_adjoint_error = _adjoint_relative(p24, V2, V4, C2, C4)
    p46_adjoint_error = _adjoint_relative(p46, V4, V6, C4, C6)
    assert p24_adjoint_error <= 1.0e-11
    assert p46_adjoint_error <= 1.0e-11
    print(
        "F0_TRANSFER_IDENTITY_AUDIT",
        {
            "composition_error": composition_error,
            "p24_interpolation_error": p24_error,
            "p46_interpolation_error": p46_error,
            "p24_adjoint_error": p24_adjoint_error,
            "p46_adjoint_error": p46_adjoint_error,
            "p24_cell_info_nonzero_count": p24.audit["cell_info_nonzero_count"],
            "p46_cell_info_nonzero_count": p46.audit["cell_info_nonzero_count"],
            "p24_active_rows": int(C4.active_rows),
            "p46_active_rows": int(C6.active_rows),
            "floquet_phase_x": complex(cfg.floquet_phase_x),
            "floquet_phase_y": complex(cfg.floquet_phase_y),
        },
    )
    p24.destroy()
    p46.destroy()
    p26.destroy()
    q6_direct.destroy()
    q6_composed.destroy()
    q6_reference.destroy()
    q6_transfer.destroy()
    q4_probe.destroy()
    q4_reference.destroy()
    q4.destroy()
    q2.destroy()
