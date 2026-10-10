"""Basix interior dual-space extraction and independent physical FE integrals.

No assembly, solve, factor, Torch, NN training or reference regeneration.
Every original J entry and orientation is used. Non-Cartesian floating
coordinate maps cannot silently inherit a Cartesian tensor-rank theorem.
"""

from itertools import product
import numpy as np


def test_definition(points, subset=False):
    degrees, values, components = [], [], []
    for component in range(3):
        maxima = [1, 1, 1]
        if not subset:
            maxima[component] = 2
        for powers in product(*[range(d+1) for d in maxima]):
            value = np.ones(len(points))
            for axis, degree in enumerate(powers):
                value *= np.sqrt(2*degree+1)*np.polynomial.legendre.legval(
                    2*points[:, axis]-1, [0]*degree+[1])
            degrees.append(powers)
            values.append(value)
            components.append(component)
    return np.asarray(degrees), np.asarray(components), np.asarray(values).T


def tensor_gauss_weights(points):
    weights = np.ones(len(points))
    for axis in range(3):
        nodes = np.unique(points[:, axis])
        gauss, w = np.polynomial.legendre.leggauss(len(nodes))
        gauss, w = (gauss+1)/2, w/2
        ids = np.argmin(abs(points[:, axis, None]-gauss), axis=1)
        if np.max(abs(points[:, axis]-gauss[ids])) > 2e-14:
            raise ValueError("INTERIOR_ORIGINAL_TENSOR_GAUSS_IDENTITY_FAILED")
        weights *= w[ids]
    return weights


def physical_targets(points, J, subset=False):
    degrees, components, values = test_definition(points, subset)
    weights = tensor_gauss_weights(points)
    determinant = float(np.linalg.det(J))
    if determinant <= 0:
        raise ValueError("POSITIVE_ORIGINAL_J_REQUIRED")
    # E_phys = E_pullback J^-1, psi_phys=psi_ref/sqrt(det J).
    targets = np.einsum("pm,p,am->map", values, weights,
                        np.linalg.inv(J)[:, components]) * np.sqrt(determinant)
    return degrees, components, targets


def interior_transform(element, J, subset=False):
    points = element.x[3][0]
    raw = element.M[3][0][..., 0]
    degrees, components, targets = physical_targets(points, J, subset)
    matrix = raw.reshape(len(raw), -1)
    transform = np.linalg.lstsq(matrix.T, targets.reshape(len(targets), -1).T,
                                rcond=None)[0].T
    error = transform @ matrix - targets.reshape(len(targets), -1)
    numerator = float(np.linalg.norm(error))
    denominator = float(np.linalg.norm(targets))
    return transform, degrees, components, dict(
        numerator=numerator, denominator=denominator, relative=numerator/denominator,
        full_J_used=True, trace_values_used=False,
        internal_dofs_from_Basix=element.entity_dofs[3][0],
        target_polynomial_degrees=degrees.tolist(), target_components=components.tolist())


def reference_local_coefficients(native, c):
    result = np.zeros(native["cell_dofs"].size, dtype=np.complex128)
    np.add.at(result, native["erows"], native["evals"]*c[native["eids"]])
    return result.reshape(native["cell_dofs"].shape)


def tensorize(cell_values, degrees, components, axis_ids, counts):
    tensors = {}
    for component, label in enumerate("xyz"):
        selected = np.flatnonzero(components == component)
        maxima = np.max(degrees[selected], axis=0)+1
        tensor = np.zeros(tuple(np.asarray(counts)*maxima), dtype=np.complex128)
        for cell, indices in enumerate(axis_ids):
            for position in selected:
                index = tuple(indices*maxima+degrees[position])
                tensor[index] = cell_values[cell, position]
        tensors[label] = tensor
    return tensors


def build_tensor(design, packet, native, c, marker):
    import basix
    from src.solvers.feinn_interpolation import full_space

    _, data, space, centers, _, _, axes = full_space(design, 3)
    element = space.element.basix_element
    if (element.dim != 144
        or not np.array_equal(element.entity_dofs[3][0], packet["interior_positions"])
        or not np.array_equal(space.dofmap.list, packet["native_cell_dofs"])):
        raise ValueError("ORIGINAL_FE_INTERIOR_OR_OWNER_IDENTITY_FAILED")
    counts = design["geometry"]["cells"]
    axis_ids = np.column_stack([
        np.searchsorted(a, centers[:, i], side="right")-1
        for i, a in enumerate(axes)])
    if len({tuple(v) for v in axis_ids}) != len(centers):
        raise ValueError("CELL_CARTESIAN_AXIS_BIJECTION_FAILED")
    msh = data.mesh
    msh.topology.create_entity_permutations()
    infos = msh.topology.get_cell_permutation_info()
    vertices = basix.cell.geometry(basix.CellType.hexahedron)
    geometry_design = np.column_stack((np.ones(8), vertices))
    local = reference_local_coefficients(native, c)
    original = local.copy()
    inverse_orientation = {}
    geometry = []
    off_axis, coordinate_dependence = 0.0, 0.0
    for cell, info in enumerate(infos):
        if int(info) not in inverse_orientation:
            matrix = np.eye(element.dim).ravel()
            space.element.T_apply(matrix, np.asarray([info], np.uint32), element.dim)
            inverse_orientation[int(info)] = matrix.reshape(element.dim, element.dim)
        original[cell] = local[cell] @ inverse_orientation[int(info)]
        x = msh.geometry.x[msh.geometry.dofmap[cell]].copy()
        x -= x[0]
        J = np.linalg.lstsq(geometry_design, x, rcond=None)[0][1:].T
        geometry.append(J)
        non_diagonal = packet["jacobians"][cell].copy()
        non_diagonal[np.arange(3), np.arange(3)] = 0
        off_axis = max(off_axis, float(np.max(abs(non_diagonal))))
        for a in range(3):
            matches = axis_ids[:, a] == axis_ids[cell, a]
            coordinate_dependence = max(coordinate_dependence,
                float(np.ptp(packet["origins"][matches, a])),
                float(np.ptp(packet["jacobians"][matches, a, a])))
    # Independent geometry and FE basis integration: no interpolation matrix.
    points, weights = basix.make_quadrature(basix.CellType.hexahedron, 15)
    full_degrees, full_components, psi = test_definition(points)
    sub_degrees, sub_components, sub_psi = test_definition(points, True)
    basis = element.tabulate(0, points)[0]
    full_coef, sub_coef, full_integral, sub_integral = [], [], [], []
    transform_defects, sub_defects, norm_energy, bessel_energy = [], [], 0.0, 0.0
    orientation_defects = []
    for cell, J in enumerate(geometry):
        unorient = np.linalg.solve(
            packet["transforms"][packet["orientation_ids"][cell]], local[cell])
        orientation_defects.append(float(np.linalg.norm(unorient-original[cell])))
        coefficient_moments = unorient[packet["interior_positions"]]
        transform, _, _, report = interior_transform(element, packet["jacobians"][cell])
        sub_transform, _, _, sub_report = interior_transform(element, packet["jacobians"][cell], True)
        full_coef.append(transform @ coefficient_moments)
        sub_coef.append(sub_transform @ coefficient_moments)
        transform_defects.append(report["relative"])
        sub_defects.append(sub_report["relative"])
        E = np.einsum("i,pia->pa", original[cell], basis) @ np.linalg.inv(J)
        determinant = float(np.linalg.det(J))
        integral = np.einsum("pm,pm,p->m", E[:, full_components], psi, weights) * np.sqrt(determinant)
        sub_value = np.einsum("pm,pm,p->m", E[:, sub_components], sub_psi, weights) * np.sqrt(determinant)
        full_integral.append(integral)
        sub_integral.append(sub_value)
        norm_energy += float(np.dot(weights, np.sum(abs(E)**2, axis=1))*determinant)
        bessel_energy += float(np.vdot(integral, integral).real)
        if cell % 64 == 0:
            marker("interior_cells_completed", dict(cells=cell+1, total_cells=len(geometry)))
    full_coef, full_integral = np.asarray(full_coef), np.asarray(full_integral)
    sub_coef, sub_integral = np.asarray(sub_coef), np.asarray(sub_integral)
    pair = float(np.linalg.norm(full_coef-full_integral)/np.linalg.norm(full_integral))
    sub_pair = float(np.linalg.norm(sub_coef-sub_integral)/np.linalg.norm(sub_integral))
    # Do not zero these entries and then claim a theorem about arbitrary core
    # functions: their sensitivity is not bounded by a saved-state pairing.
    transferable = off_axis == 0.0 and coordinate_dependence == 0.0
    proof = dict(
        reference_E_norm=float(np.sqrt(norm_energy)), reference_E_energy=norm_energy,
        interior_moment_energy=bessel_energy, Bessel_ratio=bessel_energy/norm_energy,
        normalization="physical L2 orthonormal cell Legendre, detJ^-1/2",
        independent_integral_relative=pair, subset_independent_integral_relative=sub_pair,
        max_functional_transform_relative=max(transform_defects),
        subset_max_functional_transform_relative=max(sub_defects),
        original_orientation_pair_absolute=max(orientation_defects),
        original_J_non_diagonal_max_nm=off_axis,
        original_axis_origin_or_width_nonseparability_max_nm=coordinate_dependence,
        original_J_was_zeroed=False,
        rank_bound_transferable_to_actual_FE=transferable,
        rank_scope="actual saved FE" if transferable else "conditional Cartesian mathematical chart ONLY",
        rank_failure_reason=None if transferable else "FINITE_SAVED_J_AND_AXIS_MAP_NOT_EXACTLY_SEPARABLE_NO_UNIFORM_ALL_WEIGHT_PERTURBATION_BOUND",
        numerical_moment_pairing_pass=bool(max(pair, sub_pair)<=1e-10 and max(transform_defects)<=1e-12),
        full_internal_test_degrees=["Q(2,1,1)","Q(1,2,1)","Q(1,1,2)"],
        fallback_test_degrees="Q(1,1,1) for all three physical components",
        exact_fallback_row_space_for_affine_component_mixing=True,
        MPC_internal_owner_independent=True,
        interior_owner_unique_count=int(len(np.unique(packet["owner_rows"][:, packet["interior_positions"]]))),
        original_rows=int(packet["active_rows"]), cells=len(centers),
        reference_exposed=True, pde_only_solve=False, production_initialization_allowed=False,
        FE_assembly_count=0, solve_count=0, factor_count=0)
    return dict(
        full=tensorize(full_coef, full_degrees, full_components, axis_ids, counts),
        independent=tensorize(full_integral, full_degrees, full_components, axis_ids, counts),
        subset=tensorize(sub_coef, sub_degrees, sub_components, axis_ids, counts),
        subset_independent=tensorize(sub_integral, sub_degrees, sub_components, axis_ids, counts),
        report=proof, axis_ids=axis_ids,
        transform_example=interior_transform(element, packet["jacobians"][0])[0])
