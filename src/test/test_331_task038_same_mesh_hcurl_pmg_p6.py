"""Focused tests for the exact constrained same-mesh Jacobi diagonal."""

from __future__ import annotations

import numpy as np
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    build_small_same_mesh_positive_case,
    destroy_small_same_mesh_positive_case,
    same_mesh_positive_form,
)
from src.solvers.fullspace_lor_native_hx_fixture import (
    _piecewise_positive_coefficients,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import (
    accumulate_constrained_local_diagonal,
    build_constrained_jacobi_diagonal,
)


def test_constrained_local_diagonal_keeps_multi_master_cross_terms():
    factor = np.asarray(
        [
            [1.4 + 0.0j, 0.2 - 0.3j, 0.1 + 0.2j, 0.1 - 0.1j],
            [0.0 + 0.0j, 1.1 + 0.0j, -0.2 + 0.1j, 0.2 + 0.0j],
            [0.0 + 0.0j, 0.0 + 0.0j, 0.8 + 0.0j, 0.3 + 0.1j],
            [0.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j, 0.9 + 0.0j],
        ],
        dtype=np.complex128,
    )
    local_tensor = factor.conj().T @ factor
    target_indices = np.asarray(
        [[0, 1], [0, -1], [1, -1], [2, -1]], dtype=np.int64
    )
    expansion_coefficients = np.asarray(
        [
            [1.0 + 0.0j, 0.35 - 0.2j],
            [0.5 + 0.25j, 0.0j],
            [1.0 + 0.0j, 0.0j],
            [1.0 + 0.0j, 0.0j],
        ],
        dtype=np.complex128,
    )
    observed = np.zeros(3, dtype=np.complex128)
    accumulate_constrained_local_diagonal(
        local_tensor,
        target_indices,
        expansion_coefficients,
        observed,
    )
    expansion = np.asarray(
        [
            [1.0 + 0.0j, 0.35 - 0.2j, 0.0j],
            [0.5 + 0.25j, 0.0j, 0.0j],
            [0.0j, 1.0 + 0.0j, 0.0j],
            [0.0j, 0.0j, 1.0 + 0.0j],
        ],
        dtype=np.complex128,
    )
    expected = np.diag(expansion.conj().T @ local_tensor @ expansion)
    np.testing.assert_allclose(observed, expected, rtol=0.0, atol=1.0e-13)
    assert np.count_nonzero(target_indices[0] >= 0) == 2
    assert abs(local_tensor[0, 1]) > 0.0


def test_p6_one_cell_kernel_transform_diagonal_is_positive():
    unit_cube = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.ones(3)],
        [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(
        unit_cube,
        element("N1curl", unit_cube.basix_cell(), 6, dtype=default_real_type),
    )
    form = same_mesh_positive_form(
        space,
        curl_coefficient=1.0,
        mass_coefficient=0.25,
    )
    compiled = fem.form(form)
    diagonal = build_constrained_jacobi_diagonal(compiled)
    try:
        values = np.asarray(diagonal.array, dtype=np.complex128)
        assert values.size == int(space.element.space_dimension)
        assert values.size > 0
        assert np.all(np.isfinite(values))
        assert np.all(values.real > 0.0)
        assert np.max(np.abs(values.imag)) <= 1.0e-13
    finally:
        diagonal.destroy()


def test_p3_h50_constrained_diagonal_matches_assembled_mpc_matrix():
    cfg = target_stage4_config(degree=3, h_nm=50.0)
    case = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name="random"
    )
    first = second = reference = difference = None
    mu = mass = None
    try:
        mu, mass, _ = _piecewise_positive_coefficients(
            case["mesh"], case["mesh_data"].cell_tags, cfg
        )
        mu_before = np.array(mu.x.array, copy=True)
        mass_before = np.array(mass.x.array, copy=True)
        source_before = np.array(case["source"].array, copy=True)
        bilinear_form = same_mesh_positive_form(
            case["fine_space"], curl_coefficient=mu, mass_coefficient=mass
        )
        compiled = fem.form(bilinear_form)
        first = build_constrained_jacobi_diagonal(
            compiled, case["fine_floquet"].mpc
        )
        second = build_constrained_jacobi_diagonal(
            compiled, case["fine_floquet"].mpc
        )
        reference = case["fine_matrix"].createVecRight()
        case["fine_matrix"].getDiagonal(reference)
        difference = first.copy()
        difference.axpy(-1.0, reference)
        denominator = max(
            float(reference.norm()), np.finfo(np.float64).tiny
        )
        relative = float(difference.norm()) / denominator
        local_max = float(
            np.max(np.abs(np.asarray(difference.array, dtype=np.complex128)))
        )
        max_abs = float(
            MPI.COMM_WORLD.allreduce(local_max, op=MPI.MAX)
        )
        repeat = first.copy()
        repeat.axpy(-1.0, second)
        try:
            repeat_relative = float(repeat.norm()) / max(
                float(second.norm()), np.finfo(np.float64).tiny
            )
        finally:
            repeat.destroy()
        assert relative <= 1.0e-11
        assert max_abs <= 1.0e-10
        assert repeat_relative <= 1.0e-13
        assert np.all(np.isfinite(np.asarray(first.array)))
        assert np.all(np.asarray(first.array).real > 0.0)
        np.testing.assert_array_equal(mu.x.array, mu_before)
        np.testing.assert_array_equal(mass.x.array, mass_before)
        np.testing.assert_array_equal(case["source"].array, source_before)
        cell_info = np.asarray(
            case["fine_space"].mesh.topology.get_cell_permutation_info(),
            dtype=np.uint32,
        )
        assert np.count_nonzero(cell_info) > 0
    finally:
        for vector in (difference, reference, second, first):
            if vector is not None:
                vector.destroy()
        del mu, mass
        destroy_small_same_mesh_positive_case(case)
