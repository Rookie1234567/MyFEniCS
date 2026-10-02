"""Bounded reference-metric path for the exact positive H(curl) diagonal."""
from __future__ import annotations

import numpy as np
from dolfinx.la.petsc import create_vector
from petsc4py import PETSc

from .fullspace_quadrature_diagonal import (
    PositiveCellBasis,
    _affine_cell_jacobian,
    accumulate_basis_energy,
)
from .fullspace_same_mesh_hcurl_pmg_p6 import (
    _cell_expansion_workspace,
    _fill_cell_expansion,
    _mpc_expansion_metadata,
)

_METRIC_CACHE_LIMIT = 64
_TRANSFORM_CACHE_LIMIT = 64


def _reference_energy_tensors(values, curls, weights):
    """Integrate component-pair reference energies using the original rule."""
    if (
        values.ndim != 3
        or curls.shape != values.shape
        or weights.shape != (values.shape[1],)
        or values.shape[2] != 3
        or not all(np.all(np.isfinite(array)) for array in (values, curls, weights))
    ):
        raise ValueError("invalid reference basis energy inputs")
    mass = np.einsum(
        "q,iqk,iql->ikl", weights, values.conj(), values, optimize=True
    )
    curl = np.einsum(
        "q,iqk,iql->ikl", weights, curls.conj(), curls, optimize=True
    )
    return np.ascontiguousarray(mass), np.ascontiguousarray(curl)


def _oriented_reference_energy_tensors(element, values, curls, weights, permutation):
    """Integrate exact per-basis tensors after the real Basix cell transform."""
    oriented_values = np.array(values, copy=True, order="C")
    oriented_curls = np.array(curls, copy=True, order="C")
    if element.needs_dof_transformations:
        info = np.asarray([permutation], dtype=np.uint32)
        block_size = oriented_values.shape[1] * oriented_values.shape[2]
        element.T_apply(oriented_values.reshape(-1), info, block_size)
        element.T_apply(oriented_curls.reshape(-1), info, block_size)
    tensors = _reference_energy_tensors(oriented_values, oriented_curls, weights)
    del oriented_values, oriented_curls
    return tensors


def _metric_component_diagonals(mass_tensor, curl_tensor, jacobian):
    determinant = float(np.linalg.det(jacobian))
    if not np.isfinite(determinant) or determinant <= 0.0:
        raise ValueError("positive finite Jacobian required")
    inverse = np.linalg.inv(jacobian)
    mass_metric = abs(determinant) * (inverse @ inverse.T)
    curl_metric = (jacobian.T @ jacobian) / abs(determinant)
    mass = np.einsum("iab,ab->i", mass_tensor, mass_metric, optimize=True)
    curl = np.einsum("iab,ab->i", curl_tensor, curl_metric, optimize=True)
    scale = max(float(np.max(np.abs(mass))), float(np.max(np.abs(curl))), 1.0)
    tolerance = 512 * np.finfo(np.float64).eps * scale
    if np.max(np.abs(mass.imag)) > tolerance or np.max(np.abs(curl.imag)) > tolerance:
        raise ValueError("reference metric energy acquired a non-real diagonal")
    mass = np.asarray(mass.real, dtype=np.float64)
    curl = np.asarray(curl.real, dtype=np.float64)
    return mass, curl


def build_reference_metric_positive_diagonal(
    space,
    mu,
    mass,
    mpc,
    *,
    audit=None,
):
    """Build the exact constrained diagonal from oriented reference metrics.

    Each actual Basix cell transform is applied to temporary reference basis
    values/curls before their component energy tensors are integrated. Cells
    without shared MPC targets then contract those tensors with the exact
    affine Jacobian metric. Shared targets use bounded full-basis integration
    so complex multi-master cross terms remain exact.
    """
    if PETSc.ScalarType is not np.complex128:
        raise TypeError("complex128 PETSc required")
    if mpc.function_space.mesh is not space.mesh:
        raise ValueError("MPC mesh mismatch")
    work = mpc.function_space
    if (
        work.dofmap.index_map.size_global != space.dofmap.index_map.size_global
        or work.element.space_dimension != space.element.space_dimension
    ):
        raise ValueError("MPC space mismatch")

    basis = PositiveCellBasis(space, mu, mass)
    dimension = int(work.element.space_dimension)
    if basis.values.shape[0] != dimension:
        raise ValueError("reference basis differs from the local element")

    index_map = work.dofmap.index_map
    owned = int(index_map.size_local)
    storage = owned + int(index_map.num_ghosts)
    expansion_metadata = _mpc_expansion_metadata(mpc)
    slaves, mask, targets, coefficients = _cell_expansion_workspace(
        mpc, storage, dimension, expansion_metadata=expansion_metadata
    )
    work.mesh.topology.create_entity_permutations()
    permutations = work.mesh.topology.get_cell_permutation_info()
    local = np.zeros(storage, dtype=np.complex128)
    cell_count = int(work.mesh.topology.index_map(work.mesh.topology.dim).size_local)
    orientation_tensor_cache = {}
    metric_cache = {}
    orientation_tensor_cache_hits = orientation_tensor_cache_misses = 0
    orientation_tensor_cache_bypasses = 0
    metric_cache_hits = metric_cache_misses = 0
    metric_cache_bypasses = 0
    target_merge_fallbacks = 0
    used_metric_cells = 0

    for cell in range(cell_count):
        dofs = np.asarray(work.dofmap.cell_dofs(cell), dtype=np.int32)
        _fill_cell_expansion(
            dofs, mpc, storage, mask, targets, coefficients,
            expansion_metadata=expansion_metadata,
        )
        row_counts = np.count_nonzero(targets >= 0, axis=1)
        valid_targets = targets[targets >= 0]
        has_target_merge = bool(
            np.any(row_counts > 1)
            or valid_targets.size != np.unique(valid_targets).size
        )
        permutation = int(permutations[cell])
        if has_target_merge:
            target_merge_fallbacks += 1
            values, curls, weights, (mu_cell, mass_cell) = basis.cell(
                cell, permutation
            )
            accumulate_basis_energy(
                values,
                curls,
                weights,
                targets,
                coefficients,
                local,
                curl_coefficient=mu_cell,
                mass_coefficient=mass_cell,
                batched_target_grouping=True,
            )
            del values, curls, weights
            continue

        orientation_tensors = orientation_tensor_cache.get(permutation)
        if orientation_tensors is None:
            orientation_tensors = _oriented_reference_energy_tensors(
                space.element,
                basis.values,
                basis.curls,
                basis.weights,
                permutation,
            )
            if len(orientation_tensor_cache) < _TRANSFORM_CACHE_LIMIT:
                orientation_tensor_cache[permutation] = orientation_tensors
            else:
                orientation_tensor_cache_bypasses += 1
            orientation_tensor_cache_misses += 1
        else:
            orientation_tensor_cache_hits += 1

        coordinates = work.mesh.geometry.x[work.mesh.geometry.dofmap[cell]]
        jacobian = _affine_cell_jacobian(basis.geometry_derivatives, coordinates)
        metric_key = (jacobian.tobytes(), permutation)
        component_diagonals = metric_cache.get(metric_key)
        if component_diagonals is None:
            component_diagonals = _metric_component_diagonals(
                orientation_tensors[0], orientation_tensors[1], jacobian
            )
            if len(metric_cache) < _METRIC_CACHE_LIMIT:
                metric_cache[metric_key] = component_diagonals
            else:
                metric_cache_bypasses += 1
            metric_cache_misses += 1
        else:
            metric_cache_hits += 1
        mass_cell = float(
            mass.x.array[mass.function_space.dofmap.cell_dofs(cell)[0]].real
        )
        mu_cell = float(mu.x.array[mu.function_space.dofmap.cell_dofs(cell)[0]].real)
        cell_diagonal = mass_cell * component_diagonals[0] + mu_cell * component_diagonals[1]
        single_rows = np.flatnonzero(row_counts == 1)
        single_links = np.argmax(targets[single_rows] >= 0, axis=1)
        single_targets = targets[single_rows, single_links]
        single_coefficients = coefficients[single_rows, single_links]
        np.add.at(
            local,
            single_targets,
            np.abs(single_coefficients) ** 2 * cell_diagonal[single_rows],
        )
        used_metric_cells += 1
        del orientation_tensors, component_diagonals

    vector = create_vector([(index_map, int(work.dofmap.index_map_bs))])
    try:
        with vector.localForm() as form:
            form.array_w[:] = local
        vector.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
        )
        if not np.all(np.isfinite(vector.array)) or np.any(
            vector.array.real[~mask[:owned]] <= 0
        ):
            raise ValueError("nonfinite/nonpositive constrained diagonal")
        with vector.localForm() as form:
            form.array_w[slaves[slaves < owned]] = 1
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD
        )
        if audit is not None:
            orientation_cache_bytes = int(
                sum(
                    tensor.nbytes
                    for pair in orientation_tensor_cache.values()
                    for tensor in pair
                )
            )
            metric_cache_bytes = int(
                sum(
                    component.nbytes
                    for pair in metric_cache.values()
                    for component in pair
                )
            )
            orientation_input_copy_bytes = int(
                basis.values.nbytes + basis.curls.nbytes
            )
            audit.update(
                identity="reference_energy_actual_affine_metric_v1",
                quadrature_degree=int(basis.audit["quadrature_degree"]),
                quadrature_rule=str(basis.audit["quadrature_rule"]),
                points_sha256=basis.audit["points_sha256"],
                weights_sha256=basis.audit["weights_sha256"],
                reference_basis_values_bytes=int(basis.values.nbytes),
                reference_basis_curls_bytes=int(basis.curls.nbytes),
                orientation_tensor_pair_bytes=int(
                    2 * dimension * 3 * 3 * np.dtype(
                        np.result_type(basis.values.dtype, basis.curls.dtype)
                    ).itemsize
                ),
                orientation_build_input_copy_bytes=orientation_input_copy_bytes,
                orientation_build_input_copy_bytes_per_build=orientation_input_copy_bytes,
                orientation_tensor_build_count=orientation_tensor_cache_misses,
                orientation_build_input_copy_bytes_cumulative=int(
                    orientation_input_copy_bytes * orientation_tensor_cache_misses
                ),
                orientation_build_known_array_peak_bytes=int(
                    2 * orientation_input_copy_bytes
                    + 2
                    * dimension
                    * 3
                    * 3
                    * np.dtype(
                        np.result_type(basis.values.dtype, basis.curls.dtype)
                    ).itemsize
                ),
                orientation_tensor_cache_limit=_TRANSFORM_CACHE_LIMIT,
                orientation_tensor_cache_entries=len(orientation_tensor_cache),
                orientation_tensor_cache_hits=orientation_tensor_cache_hits,
                orientation_tensor_cache_misses=orientation_tensor_cache_misses,
                orientation_tensor_cache_bypasses=orientation_tensor_cache_bypasses,
                orientation_tensor_cache_storage_bytes=orientation_cache_bytes,
                orientation_tabulation_retained_after_tensor_build=False,
                metric_cache_limit=_METRIC_CACHE_LIMIT,
                metric_cache_entries=len(metric_cache),
                metric_cache_hits=metric_cache_hits,
                metric_cache_misses=metric_cache_misses,
                metric_cache_bypasses=metric_cache_bypasses,
                metric_cache_storage_bytes=metric_cache_bytes,
                retained_cache_ndarray_storage_bytes=int(
                    orientation_cache_bytes + metric_cache_bytes
                ),
                mpc_expansion_metadata_policy="borrowed_once_for_this_build",
                mpc_coefficient_provider_calls=1,
                mpc_offsets_dtype=str(expansion_metadata[1].dtype),
                mpc_offsets_array_bytes=int(expansion_metadata[1].nbytes),
                mpc_global_offset_conversion_copies=0,
                mpc_expansion_metadata_retained_after_return=False,
                owned_cells=cell_count,
                cells_using_reference_metric=used_metric_cells,
                target_merge_fallbacks=target_merge_fallbacks,
                per_cell_physical_basis_table_builds=target_merge_fallbacks,
                actual_cell_T_apply_before_reference_integration=True,
                geometry_rounding_or_approximation=False,
                target_cross_terms_preserved_by_fallback=True,
            )
        return vector
    except BaseException:
        vector.destroy()
        raise
