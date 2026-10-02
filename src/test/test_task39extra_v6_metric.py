"""Exact reference-metric positive diagonal candidate checks."""
import numpy as np
from mpi4py import MPI

from src.solvers.fullspace_metric_positive_diagonal import (
    _metric_component_diagonals,
    _oriented_reference_energy_tensors,
    _reference_energy_tensors,
    build_reference_metric_positive_diagonal,
)
from src.solvers.fullspace_quadrature_diagonal import build_quadrature_positive_diagonal


def test_oriented_reference_metric_tensors_match_direct_physical_energy():
    rng = np.random.default_rng(3908)
    values = rng.normal(size=(5, 7, 3)) + 1j * rng.normal(size=(5, 7, 3))
    curls = rng.normal(size=(5, 7, 3)) + 1j * rng.normal(size=(5, 7, 3))
    weights = np.linspace(0.1, 0.7, 7)
    transform = np.eye(5) + np.triu(rng.normal(size=(5, 5)) * 0.07, 1)

    class DenseOrientation:
        needs_dof_transformations = True

        def T_apply(self, data, _cell_info, block_size):
            rows = data.reshape(5, block_size)
            rows[:] = transform @ rows

    element = DenseOrientation()
    mass_tensor, curl_tensor = _oriented_reference_energy_tensors(
        element, values, curls, weights, permutation=11
    )
    oriented_values = np.einsum("ij,jqk->iqk", transform, values)
    oriented_curls = np.einsum("ij,jqk->iqk", transform, curls)
    direct_tensors = _reference_energy_tensors(
        oriented_values, oriented_curls, weights
    )
    # BLAS matmul and einsum can accumulate in different orders on this ABI.
    # This bound remains far stricter than the component's 1e-10 Gate.
    np.testing.assert_allclose(mass_tensor, direct_tensors[0], rtol=1e-14, atol=1e-14)
    np.testing.assert_allclose(curl_tensor, direct_tensors[1], rtol=1e-14, atol=1e-14)

    jacobian = np.array([[1.3, 0.2, 0.1], [0.1, 0.9, 0.25], [0.0, 0.15, 1.1]])
    mass_diagonal, curl_diagonal = _metric_component_diagonals(
        mass_tensor, curl_tensor, jacobian
    )
    determinant = np.linalg.det(jacobian)
    physical_values = oriented_values @ np.linalg.inv(jacobian)
    physical_curls = oriented_curls @ jacobian.T / determinant
    expected = np.sum(
        weights[None, :, None]
        * determinant
        * (1.7 * np.abs(physical_values) ** 2 + 0.6 * np.abs(physical_curls) ** 2),
        axis=(1, 2),
    )
    actual = 1.7 * mass_diagonal + 0.6 * curl_diagonal
    np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=2e-13)


def test_actual_p3_mpc_diagonal_matches_original_quadrature():
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_lor_native_hx_fixture import (
        _piecewise_positive_coefficients,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        build_small_same_mesh_positive_case,
        destroy_small_same_mesh_positive_case,
    )

    cfg = target_stage4_config(degree=3, h_nm=50.0)
    case = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name="random"
    )
    vectors = []
    try:
        space, mpc = case["fine_space"], case["fine_floquet"].mpc
        mu, mass, _ = _piecewise_positive_coefficients(
            case["mesh"], case["mesh_data"].cell_tags, cfg
        )
        old = build_quadrature_positive_diagonal(space, mu, mass, mpc)
        vectors.append(old)
        candidate_audit = {}
        candidate = build_reference_metric_positive_diagonal(
            space, mu, mass, mpc, audit=candidate_audit
        )
        vectors.append(candidate)
        matrix_diagonal = case["fine_matrix"].createVecRight()
        vectors.append(matrix_diagonal)
        case["fine_matrix"].getDiagonal(matrix_diagonal)

        np.testing.assert_allclose(candidate.array, old.array, rtol=1e-10, atol=1e-10)
        difference = candidate.copy()
        vectors.append(difference)
        difference.axpy(-1, matrix_diagonal)
        assert difference.norm() / matrix_diagonal.norm() <= 1e-10
        assert candidate_audit["identity"] == "reference_energy_actual_affine_metric_v1"
        assert candidate_audit["actual_cell_T_apply_before_reference_integration"] is True
        assert candidate_audit["cells_using_reference_metric"] > 0
        assert candidate_audit["metric_cache_misses"] > 1
        assert candidate_audit["orientation_tensor_cache_entries"] > 0
        assert candidate_audit["orientation_tensor_cache_entries"] <= candidate_audit[
            "orientation_tensor_cache_limit"
        ]
        assert candidate_audit["target_cross_terms_preserved_by_fallback"] is True
        assert np.all(np.isfinite(candidate.array))
        assert np.all(candidate.array.real > 0)
        slaves = np.asarray(mpc.slaves)
        np.testing.assert_array_equal(
            candidate.array[slaves[slaves < candidate.getLocalSize()]], 1
        )
        assert np.count_nonzero(space.mesh.topology.get_cell_permutation_info()) > 0
    finally:
        for vector in vectors:
            vector.destroy()
        destroy_small_same_mesh_positive_case(case)


def test_reference_metric_fallback_preserves_complex_multimaster_cross_term():
    import src.solvers.fullspace_metric_positive_diagonal as metric_module
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_lor_native_hx_fixture import (
        _piecewise_positive_coefficients,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        build_small_same_mesh_positive_case,
        destroy_small_same_mesh_positive_case,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import (
        _cell_expansion_workspace,
        _fill_cell_expansion,
    )

    cfg = target_stage4_config(degree=3, h_nm=50.0)
    case = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name="random"
    )
    vectors = []
    try:
        space, real_mpc = case["fine_space"], case["fine_floquet"].mpc
        mu, mass, _ = _piecewise_positive_coefficients(
            case["mesh"], case["mesh_data"].cell_tags, cfg
        )
        index_map = real_mpc.function_space.dofmap.index_map
        storage = int(index_map.size_local + index_map.num_ghosts)
        dimension = int(space.element.space_dimension)
        _slaves, mask, targets, coefficients = _cell_expansion_workspace(
            real_mpc, storage, dimension
        )
        raw_coefficients, raw_offsets = real_mpc.coefficients()
        raw_coefficients = np.asarray(raw_coefficients, dtype=np.complex128)
        raw_offsets = np.asarray(raw_offsets, dtype=np.int64)
        selected = None
        for cell in range(
            int(space.mesh.topology.index_map(space.mesh.topology.dim).size_local)
        ):
            dofs = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
            _fill_cell_expansion(
                dofs, real_mpc, storage, mask, targets, coefficients
            )
            for local_dof in dofs.tolist():
                local_dof = int(local_dof)
                if not mask[local_dof]:
                    continue
                start, stop = raw_offsets[local_dof : local_dof + 2]
                if stop - start != 1 or abs(raw_coefficients[start].imag) <= 1e-12:
                    continue
                masters = np.asarray(
                    real_mpc.masters.links(local_dof), dtype=np.int64
                )
                local_extra = [
                    int(dof)
                    for dof in dofs.tolist()
                    if not mask[int(dof)]
                    and int(dof) != local_dof
                    and int(dof) not in masters
                ]
                if local_extra:
                    selected = (
                        int(cell),
                        local_dof,
                        int(masters[0]),
                        local_extra[0],
                        complex(raw_coefficients[start]),
                    )
                    break
            if selected is not None:
                break
        assert selected is not None, "fixture must expose a complex Floquet slave"
        selected_cell, selected_slave, original_master, extra_master, floquet_coeff = selected
        assert abs(floquet_coeff.imag) > 1e-12
        assert extra_master in np.asarray(space.dofmap.cell_dofs(selected_cell))
        original_coefficients, original_offsets = real_mpc.coefficients()
        original_coefficients = np.asarray(
            original_coefficients, dtype=np.complex128
        )
        original_offsets = np.asarray(original_offsets, dtype=np.int64)
        insertion = int(original_offsets[selected_slave + 1])
        expanded_coefficients = np.concatenate(
            (
                original_coefficients[:insertion],
                np.asarray([0.25 - 0.125j], dtype=np.complex128),
                original_coefficients[insertion:],
            )
        )
        expanded_offsets = original_offsets.copy()
        expanded_offsets[selected_slave + 1 :] += 1
        real_masters = real_mpc.masters

        class ExpandedMasters:
            def links(self, row):
                if int(row) == selected_slave:
                    return np.asarray(
                        [original_master, extra_master], dtype=np.int64
                    )
                return real_masters.links(row)

        class MultiMasterMPC:
            function_space = real_mpc.function_space
            slaves = real_mpc.slaves
            masters = ExpandedMasters()

            def coefficients(self):
                return expanded_coefficients, expanded_offsets

        mpc = MultiMasterMPC()
        reference = build_quadrature_positive_diagonal(space, mu, mass, mpc)
        vectors.append(reference)
        audit = {}
        candidate = metric_module.build_reference_metric_positive_diagonal(
            space, mu, mass, mpc, audit=audit
        )
        vectors.append(candidate)
        np.testing.assert_allclose(
            candidate.array, reference.array, rtol=1e-11, atol=1e-11
        )
        assert audit["target_merge_fallbacks"] > 0
        assert audit["target_cross_terms_preserved_by_fallback"] is True
    finally:
        for vector in vectors:
            vector.destroy()
        destroy_small_same_mesh_positive_case(case)
