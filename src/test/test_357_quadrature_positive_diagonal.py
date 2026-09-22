"""Independent dense algebra and assembled-MPC oracles for energy diagonal."""
import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from src.solvers.fullspace_quadrature_diagonal import (
    accumulate_basis_energy, build_quadrature_positive_diagonal,
)


def test_complex_cross_terms_with_nontrivial_basis_transform():
    rng = np.random.default_rng(39)
    raw = rng.normal(size=(4, 7, 3))
    transform = np.array([[1, 0.3, 0, 0], [0, -1, 0, 0],
                          [0, 0, 0, 1], [0, 0, 1, 0]])
    values = np.einsum('ij,jqk->iqk', transform, raw)
    curls = 0.7*values
    weights = np.arange(1, 8)/28
    targets = np.array([[0, 1], [0, -1], [1, 2], [2, -1]])
    c = np.array([[1, .3+.2j], [.2-.5j, 0], [1j, .8], [1, 0]])
    expansion = np.zeros((4, 3), complex)
    for i, j in zip(*np.nonzero(targets >= 0)):
        expansion[i, targets[i, j]] += c[i, j]
    dense = 1.98*np.einsum('iqk,jqk,q->ij', values, values, weights)
    expected = np.diag(expansion.conj().T @ dense @ expansion)
    result = np.zeros(3, complex)
    accumulate_basis_energy(values, curls, weights, targets, c, result,
                            curl_coefficient=2., mass_coefficient=1.)
    np.testing.assert_allclose(result, expected, rtol=1e-13, atol=1e-13)
    batched = np.zeros(3, complex)
    accumulate_basis_energy(
        values,
        curls,
        weights,
        targets,
        c,
        batched,
        curl_coefficient=2.,
        mass_coefficient=1.,
        batched_target_grouping=True,
    )
    np.testing.assert_allclose(batched, result, rtol=1e-13, atol=1e-13)
    with pytest.raises(ValueError):
        accumulate_basis_energy(values*np.nan, curls, weights, targets, c, result,
                                curl_coefficient=2., mass_coefficient=1.)


def test_batched_target_grouping_mixes_singletons_and_repeated_targets():
    rng = np.random.default_rng(3901)
    values = rng.normal(size=(5, 4, 3)) + 1j * rng.normal(size=(5, 4, 3))
    curls = rng.normal(size=(5, 4, 3)) + 1j * rng.normal(size=(5, 4, 3))
    weights = np.array([0.2, 0.3, 0.1, 0.4])
    targets = np.array([[0, -1], [1, -1], [0, 2], [3, -1], [2, -1]])
    coefficients = np.array(
        [[1.0, 0.0], [0.3 + 0.2j, 0.0], [0.5 - 0.1j, -0.7j],
         [1.0, 0.0], [0.8 + 0.4j, 0.0]],
        dtype=np.complex128,
    )
    expansion = np.zeros((len(values), 4), dtype=np.complex128)
    for row, link in zip(*np.nonzero(targets >= 0)):
        expansion[row, targets[row, link]] += coefficients[row, link]
    gram = (
        1.7 * np.einsum("iqk,jqk,q->ij", values.conj(), values, weights)
        + 0.6 * np.einsum("iqk,jqk,q->ij", curls.conj(), curls, weights)
    )
    expected = np.diag(expansion.conj().T @ gram @ expansion)
    default = np.zeros(4, dtype=np.complex128)
    batched = np.zeros(4, dtype=np.complex128)
    for output, enabled in ((default, False), (batched, True)):
        accumulate_basis_energy(
            values,
            curls,
            weights,
            targets,
            coefficients,
            output,
            curl_coefficient=0.6,
            mass_coefficient=1.7,
            batched_target_grouping=enabled,
        )
    np.testing.assert_allclose(default, expected, rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(batched, expected, rtol=1e-13, atol=1e-13)


def test_p3_assembled_mpc_repeat_inputs_slaves_ghosts():
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        build_small_same_mesh_positive_case, destroy_small_same_mesh_positive_case,
    )
    from src.solvers.fullspace_lor_native_hx_fixture import _piecewise_positive_coefficients
    cfg = target_stage4_config(degree=3, h_nm=50.)
    case = build_small_same_mesh_positive_case(cfg, MPI.COMM_WORLD, source_name='random')
    vectors = []
    try:
        space, mpc = case['fine_space'], case['fine_floquet'].mpc
        mu, mass, _ = _piecewise_positive_coefficients(case['mesh'], case['mesh_data'].cell_tags, cfg)
        before = [a.copy() for a in (mu.x.array, mass.x.array, case['source'].array)]
        first = build_quadrature_positive_diagonal(space, mu, mass, mpc); vectors.append(first)
        second = build_quadrature_positive_diagonal(space, mu, mass, mpc); vectors.append(second)
        diagonal_audit = {}
        batched = build_quadrature_positive_diagonal(
            space,
            mu,
            mass,
            mpc,
            batched_target_grouping=True,
            reuse_local_types=True,
            audit=diagonal_audit,
        )
        vectors.append(batched)
        reference = case['fine_matrix'].createVecRight(); vectors.append(reference)
        case['fine_matrix'].getDiagonal(reference)
        difference = first.copy(); vectors.append(difference)
        difference.axpy(-1, reference)
        relative = difference.norm()/reference.norm()
        assert relative <= 1e-11
        np.testing.assert_array_equal(first.array, second.array)
        np.testing.assert_allclose(batched.array, first.array, rtol=1e-12, atol=1e-12)
        assert diagonal_audit["local_type_reuse_opt_in"] is True
        assert diagonal_audit["merged_cell_fallbacks"] >= 0
        for a, b in zip((mu.x.array, mass.x.array, case['source'].array), before):
            np.testing.assert_array_equal(a, b)
        assert np.all(np.isfinite(first.array)) and np.all(first.array.real > 0)
        slaves = np.asarray(mpc.slaves)
        np.testing.assert_array_equal(first.array[slaves[slaves < first.getLocalSize()]], 1)
        from dolfinx.la.petsc import create_vector
        ghost_reference = create_vector([(mpc.function_space.dofmap.index_map, 1)])
        vectors.append(ghost_reference)
        ghost_reference.array[:] = reference.array
        ghost_reference.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
        with first.localForm() as a, ghost_reference.localForm() as b:
            np.testing.assert_allclose(a.array, b.array, rtol=1e-11, atol=1e-10)
        assert np.count_nonzero(space.mesh.topology.get_cell_permutation_info()) > 0
        print('p3 assembled MPC relative error', relative, 'rank', MPI.COMM_WORLD.rank, flush=True)
    finally:
        for v in vectors:
            v.destroy()
        destroy_small_same_mesh_positive_case(case)
