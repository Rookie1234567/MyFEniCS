from __future__ import annotations

import math
from typing import Any

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, fem, geometry, mesh


def _global_scalar(msh: mesh.Mesh, expression) -> complex:
    local = fem.assemble_scalar(fem.form(expression))
    return complex(msh.comm.allreduce(local, op=MPI.SUM))


def _nonnegative_real(value: complex) -> float:
    tolerance = 1.0e-11 * max(1.0, abs(value.real))
    if abs(value.imag) > tolerance:
        raise RuntimeError(f"Squared norm is not real: {value!r}")
    return max(0.0, float(value.real))


def _nedelec_space(msh: mesh.Mesh, degree: int):
    finite_element = element(
        "N1curl", msh.basix_cell(), degree, dtype=default_real_type
    )
    return fem.functionspace(msh, finite_element)


def _fixed_probe_values(field: fem.Function, points: np.ndarray) -> np.ndarray:
    """Evaluate fixed probes using scalar-size reductions, never a field gather."""

    msh = field.function_space.mesh
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    owned_cells = msh.topology.index_map(msh.topology.dim).size_local
    local_values = np.zeros((len(points), 3), dtype=np.complex128)
    local_counts = np.zeros(len(points), dtype=np.int32)
    for point_index in range(len(points)):
        owned = [
            int(cell)
            for cell in collisions.links(point_index)
            if int(cell) < owned_cells
        ]
        if owned:
            value = field.eval(
                points[point_index : point_index + 1],
                np.asarray([owned[0]], dtype=np.int32),
            )
            local_values[point_index] = np.asarray(value).reshape((-1, 3))[0]
            local_counts[point_index] = 1
    values = np.zeros_like(local_values)
    counts = np.zeros_like(local_counts)
    msh.comm.Allreduce(local_values, values, op=MPI.SUM)
    msh.comm.Allreduce(local_counts, counts, op=MPI.SUM)
    if np.any(counts == 0):
        raise RuntimeError("A fixed FE probe has no owning cell.")
    return values / counts[:, None]


def _distributed_cell_identity(msh: mesh.Mesh) -> dict[str, Any]:
    index_map = msh.topology.index_map(msh.topology.dim)
    start, end = index_map.local_range
    ids = np.arange(start, end, dtype=np.int64)
    local = np.asarray(
        [len(ids), np.sum(ids, dtype=np.int64), np.sum(ids * ids, dtype=np.int64)],
        dtype=np.int64,
    )
    actual = np.zeros(3, dtype=np.int64)
    msh.comm.Allreduce(local, actual, op=MPI.SUM)
    count = int(index_map.size_global)
    expected = np.asarray(
        [
            count,
            count * (count - 1) // 2,
            count * (count - 1) * (2 * count - 1) // 6,
        ],
        dtype=np.int64,
    )
    return {
        "pass": bool(np.array_equal(actual, expected)),
        "global_cell_count": count,
        "actual_count_sum_sumsq": actual.tolist(),
        "expected_count_sum_sumsq": expected.tolist(),
        "reduction": "owned_cell_scalar_allreduce_no_cell_or_field_gather",
    }


def _plane_wave_case(degree: int, cells_per_axis: int = 2) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    msh = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [cells_per_axis] * 3,
        cell_type=mesh.CellType.hexahedron,
    )
    space = _nedelec_space(msh, degree)
    wave_vector = np.asarray([0.43, -0.31, 1.17], dtype=float)
    polarization = np.asarray([0.31, 0.43, 0.0], dtype=float)
    polarization /= np.linalg.norm(polarization)
    field = fem.Function(space, name=f"B1_plane_wave_p{degree}")

    def evaluate(x):
        phase = np.exp(1j * np.dot(wave_vector, x))
        return polarization[:, None] * phase[None, :]

    field.interpolate(evaluate)
    field.x.scatter_forward()

    x = ufl.SpatialCoordinate(msh)
    phase = ufl.exp(
        1j
        * (
            wave_vector[0] * x[0]
            + wave_vector[1] * x[1]
            + wave_vector[2] * x[2]
        )
    )
    exact = ufl.as_vector(tuple(complex(value) * phase for value in polarization))
    error = field - exact
    error_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(error, error) * ufl.dx)
    )
    exact_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(exact, exact) * ufl.dx)
    )
    strong = ufl.curl(ufl.curl(field)) - float(np.dot(wave_vector, wave_vector)) * field
    h = ufl.CellDiameter(msh)
    volume_squared = _nonnegative_real(
        _global_scalar(
            msh,
            (h / degree) ** 2 * ufl.inner(strong, strong) * ufl.dx,
        )
    )
    normal = ufl.FacetNormal(msh)
    curl_jump = ufl.cross(
        normal("+"), ufl.curl(field)("+") - ufl.curl(field)("-")
    )
    jump_squared = _nonnegative_real(
        _global_scalar(
            msh,
            ufl.avg(h / degree)
            * ufl.inner(curl_jump, curl_jump)
            * ufl.dS,
        )
    )

    epsilon = 1.0e-9
    transverse = ((0.27, 0.41), (0.63, 0.72), (0.38, 0.81))
    x_master = np.asarray([[epsilon, y, z] for y, z in transverse])
    x_slave = np.asarray([[1.0 - epsilon, y, z] for y, z in transverse])
    y_master = np.asarray([[xv, epsilon, z] for xv, z in transverse])
    y_slave = np.asarray([[xv, 1.0 - epsilon, z] for xv, z in transverse])
    probe_points = np.vstack((x_master, x_slave, y_master, y_slave))
    values = _fixed_probe_values(field, probe_points)
    block = len(transverse)
    x0, x1, y0, y1 = (
        values[index * block : (index + 1) * block] for index in range(4)
    )
    x_phase = np.exp(1j * wave_vector[0] * (1.0 - 2.0 * epsilon))
    y_phase = np.exp(1j * wave_vector[1] * (1.0 - 2.0 * epsilon))
    x_exact_defect = x1[:, 1:] - x_phase * x0[:, 1:]
    y_exact_defect = y1[:, (0, 2)] - y_phase * y0[:, (0, 2)]
    exact_trace = float(
        math.sqrt(
            np.vdot(x_exact_defect, x_exact_defect).real
            + np.vdot(y_exact_defect, y_exact_defect).real
        )
    )
    orientation_fault = float(np.linalg.norm(x1[:, 1:] + x_phase * x0[:, 1:]))
    phase_fault = float(
        np.linalg.norm(x1[:, 1:] - np.exp(0.19j) * x_phase * x0[:, 1:])
    )
    dof_map = space.dofmap.index_map
    return {
        "degree": degree,
        "mesh_cells_per_axis": cells_per_axis,
        "global_cells": msh.topology.index_map(msh.topology.dim).size_global,
        "global_nedelec_dofs": dof_map.size_global * space.dofmap.index_map_bs,
        "relative_l2_field_error": math.sqrt(error_squared / exact_squared),
        "r1_volume_squared": volume_squared,
        "r1_curl_jump_squared": jump_squared,
        "r1_indicator": math.sqrt(volume_squared + jump_squared),
        "floquet_pair_residual": exact_trace,
        "orientation_fault_residual": orientation_fault,
        "phase_fault_residual": phase_fault,
        "cell_identity": _distributed_cell_identity(msh),
    }


def run_b1_periodic_nedelec_fixture() -> dict[str, Any]:
    points = [_plane_wave_case(1), _plane_wave_case(2)]
    passed = (
        all(point["cell_identity"]["pass"] for point in points)
        and all(point["floquet_pair_residual"] < 1.0e-9 for point in points)
        and all(point["orientation_fault_residual"] > 1.0e-2 for point in points)
        and all(point["phase_fault_residual"] > 1.0e-3 for point in points)
        and points[1]["relative_l2_field_error"]
        < points[0]["relative_l2_field_error"]
    )
    return {
        "name": "B1_real_periodic_nedelec_hcurl",
        "status": "real_fe_fixture_pass" if passed else "real_fe_fixture_fail",
        "real_fe": True,
        "pde_run": False,
        "mpi_size": MPI.COMM_WORLD.size,
        "space": "Basix N1curl on a 3D hexahedral mesh",
        "residual": "actual UFL cell curl-curl residual plus interior curl jump",
        "floquet_check": "fixed tangential FE probes with scalar-size allreduce",
        "points": points,
    }


def _layer_field_values(x: np.ndarray, *, k0: float, n_top: complex, n_bottom: complex):
    reflection = (n_top - n_bottom) / (n_top + n_bottom)
    transmission = 2.0 * n_top / (n_top + n_bottom)
    distance = x[2] - 0.5
    top = np.exp(-1j * k0 * n_top * distance) + reflection * np.exp(
        1j * k0 * n_top * distance
    )
    bottom = transmission * np.exp(-1j * k0 * n_bottom * distance)
    electric_y = np.where(x[2] >= 0.5 - 1.0e-12, top, bottom)
    result = np.zeros((3, x.shape[1]), dtype=np.complex128)
    result[1] = electric_y
    return result


def _reflection_amplitude(
    field: fem.Function, ds_top, *, incident_top: complex, k_top: complex
) -> complex:
    msh = field.function_space.mesh
    area = _global_scalar(msh, 1.0 * ds_top)
    mean_y = _global_scalar(msh, field[1] * ds_top) / area
    return (mean_y - incident_top) * np.exp(-0.5j * k_top)


def _layer_case(degree: int, transverse_cells: int) -> dict[str, Any]:
    comm = MPI.COMM_WORLD
    msh = mesh.create_box(
        comm,
        [np.zeros(3), np.ones(3)],
        [transverse_cells, transverse_cells, 2 * transverse_cells],
        cell_type=mesh.CellType.hexahedron,
    )
    space = _nedelec_space(msh, degree)
    k0 = 2.3
    n_top = 1.0 + 0.0j
    n_bottom = 1.45 + 0.12j
    reflection = (n_top - n_bottom) / (n_top + n_bottom)
    transmission = 2.0 * n_top / (n_top + n_bottom)
    field = fem.Function(space, name=f"B2_lossy_layer_p{degree}")
    field.interpolate(
        lambda coordinates: _layer_field_values(
            coordinates, k0=k0, n_top=n_top, n_bottom=n_bottom
        )
    )
    field.x.scatter_forward()

    epsilon_space = fem.functionspace(msh, ("DG", 0))
    epsilon_r = fem.Function(epsilon_space, name="B2_piecewise_complex_epsilon")
    epsilon_r.interpolate(
        lambda coordinates: np.where(
            coordinates[2] >= 0.5 - 1.0e-12, n_top**2, n_bottom**2
        )
    )
    epsilon_r.x.scatter_forward()

    x = ufl.SpatialCoordinate(msh)
    distance = x[2] - 0.5
    top_y = ufl.exp(-1j * k0 * n_top * distance) + reflection * ufl.exp(
        1j * k0 * n_top * distance
    )
    bottom_y = transmission * ufl.exp(-1j * k0 * n_bottom * distance)
    exact_y = ufl.conditional(ufl.ge(x[2], 0.5), top_y, bottom_y)
    exact = ufl.as_vector((0.0, exact_y, 0.0))
    error = field - exact
    error_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(error, error) * ufl.dx)
    )
    exact_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(exact, exact) * ufl.dx)
    )

    strong = ufl.curl(ufl.curl(field)) - k0**2 * epsilon_r * field
    h = ufl.CellDiameter(msh)
    volume_squared = _nonnegative_real(
        _global_scalar(
            msh,
            (h / degree) ** 2 * ufl.inner(strong, strong) * ufl.dx,
        )
    )
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    interface_facets = mesh.locate_entities(
        msh,
        msh.topology.dim - 1,
        lambda coordinates: np.isclose(coordinates[2], 0.5),
    )
    interface_tags = mesh.meshtags(
        msh,
        msh.topology.dim - 1,
        np.asarray(sorted(interface_facets), dtype=np.int32),
        np.ones(len(interface_facets), dtype=np.int32),
    )
    dS = ufl.Measure("dS", domain=msh, subdomain_data=interface_tags)
    normal = ufl.FacetNormal(msh)
    flux_jump = ufl.cross(
        normal("+"), ufl.curl(field)("+") - ufl.curl(field)("-")
    )
    interface_squared = _nonnegative_real(
        _global_scalar(
            msh,
            ufl.avg(h / degree)
            * ufl.inner(flux_jump, flux_jump)
            * dS(1),
        )
    )

    top_facets = mesh.locate_entities_boundary(
        msh,
        msh.topology.dim - 1,
        lambda coordinates: np.isclose(coordinates[2], 1.0),
    )
    top_tags = mesh.meshtags(
        msh,
        msh.topology.dim - 1,
        np.asarray(sorted(top_facets), dtype=np.int32),
        np.full(len(top_facets), 2, dtype=np.int32),
    )
    ds_top = ufl.Measure("ds", domain=msh, subdomain_data=top_tags)(2)
    k_top = k0 * n_top
    incident_top = np.exp(-0.5j * k_top)
    amplitude = _reflection_amplitude(
        field, ds_top, incident_top=incident_top, k_top=k_top
    )
    reflectance = abs(amplitude) ** 2

    direction = fem.Function(space, name="B2_goal_direction")
    direction.interpolate(
        lambda coordinates: np.vstack(
            (
                np.zeros(coordinates.shape[1]),
                np.full(coordinates.shape[1], 0.37 + 0.19j),
                np.zeros(coordinates.shape[1]),
            )
        )
    )
    direction.x.scatter_forward()
    direction_amplitude = (
        _global_scalar(msh, direction[1] * ds_top)
        / _global_scalar(msh, 1.0 * ds_top)
        * np.exp(-0.5j * k_top)
    )
    derivative = 2.0 * float(np.real(np.conj(amplitude) * direction_amplitude))
    step = 1.0e-6
    shifted = []
    for sign in (-1.0, 1.0):
        perturbed = fem.Function(space)
        perturbed.x.array[:] = field.x.array + sign * step * direction.x.array
        perturbed.x.scatter_forward()
        shifted_amplitude = _reflection_amplitude(
            perturbed, ds_top, incident_top=incident_top, k_top=k_top
        )
        shifted.append(abs(shifted_amplitude) ** 2)
    finite_difference = (shifted[1] - shifted[0]) / (2.0 * step)

    incident_derivative = -1j * k_top * incident_top
    derivative_total = -ufl.curl(field)[0]
    reflected_trace = field[1] - complex(incident_top)
    exact_dtn = (
        derivative_total
        - complex(incident_derivative)
        - 1j * complex(k_top) * reflected_trace
    )
    perturbed_dtn = (
        derivative_total
        - complex(incident_derivative)
        - 1.2j * complex(k_top) * reflected_trace
    )
    dtn_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(exact_dtn, exact_dtn) * ds_top)
    )
    perturbed_dtn_squared = _nonnegative_real(
        _global_scalar(msh, ufl.inner(perturbed_dtn, perturbed_dtn) * ds_top)
    )
    operator_perturbation = perturbed_dtn - exact_dtn
    operator_perturbation_squared = _nonnegative_real(
        _global_scalar(
            msh,
            ufl.inner(operator_perturbation, operator_perturbation) * ds_top,
        )
    )
    estimator = math.sqrt(volume_squared + interface_squared + dtn_squared)
    dof_map = space.dofmap.index_map
    return {
        "degree": degree,
        "transverse_cells": transverse_cells,
        "effective_h_over_p": 1.0 / (2.0 * transverse_cells * degree),
        "global_cells": msh.topology.index_map(msh.topology.dim).size_global,
        "global_nedelec_dofs": dof_map.size_global * space.dofmap.index_map_bs,
        "relative_l2_field_error": math.sqrt(error_squared / exact_squared),
        "r1_volume_squared": volume_squared,
        "material_interface_jump_squared": interface_squared,
        "external_dtn_boundary_squared": dtn_squared,
        "r1_indicator": estimator,
        "r2_kh_over_p_diagnostic": abs(k0 * n_bottom)
        / (2.0 * transverse_cells * degree),
        "reflection_amplitude_real": float(amplitude.real),
        "reflection_amplitude_imag": float(amplitude.imag),
        "reflection_amplitude_error": float(abs(amplitude - reflection)),
        "official_fixture_r00": float(reflectance),
        "exact_r00": float(abs(reflection) ** 2),
        "official_fixture_r00_error": float(abs(reflectance - abs(reflection) ** 2)),
        "goal_derivative_analytic": derivative,
        "goal_derivative_finite_difference": float(finite_difference),
        "goal_derivative_absolute_error": float(abs(derivative - finite_difference)),
        "dtn_perturbation_ratio": math.sqrt(perturbed_dtn_squared)
        / max(math.sqrt(dtn_squared), 1.0e-30),
        "dtn_operator_perturbation_norm": math.sqrt(
            operator_perturbation_squared
        ),
        "material_values": {
            "top_epsilon_real": float((n_top**2).real),
            "top_epsilon_imag": float((n_top**2).imag),
            "bottom_epsilon_real": float((n_bottom**2).real),
            "bottom_epsilon_imag": float((n_bottom**2).imag),
        },
        "cell_identity": _distributed_cell_identity(msh),
    }


def run_b2_flat_lossy_layer_fixture() -> dict[str, Any]:
    points = [_layer_case(1, 1), _layer_case(1, 2), _layer_case(2, 2)]
    passed = (
        all(point["cell_identity"]["pass"] for point in points)
        and points[-1]["relative_l2_field_error"]
        < points[0]["relative_l2_field_error"]
        and all(point["official_fixture_r00_error"] < 1.0e-10 for point in points)
        and points[-1]["r1_indicator"] < points[0]["r1_indicator"]
        and all(point["goal_derivative_absolute_error"] < 1.0e-8 for point in points)
        and all(
            point["dtn_operator_perturbation_norm"] > 1.0e-3 for point in points
        )
    )
    return {
        "name": "B2_real_flat_lossy_layer_official_goal",
        "status": "real_fe_official_goal_fixture_pass"
        if passed
        else "real_fe_official_goal_fixture_fail",
        "real_fe": True,
        "pde_run": False,
        "mpi_size": MPI.COMM_WORLD.size,
        "material": "actual piecewise-complex DG0 epsilon on an interface-aligned mesh",
        "official_goal": "fixture-normalized zero-order reflected power from the actual FE trace",
        "r2_policy": "diagnostic_only_kh_over_p_never_rescales_R1",
        "points": points,
    }


def run_real_fe_fixture_suite() -> dict[str, Any]:
    b1 = run_b1_periodic_nedelec_fixture()
    b2 = run_b2_flat_lossy_layer_fixture()
    passed = b1["status"] == "real_fe_fixture_pass" and b2["status"] == (
        "real_fe_official_goal_fixture_pass"
    )
    return {
        "schema_version": "task035.real-fe-fixtures.v1",
        "status": "real_fe_fixture_minimum_pass" if passed else "real_fe_fixture_minimum_fail",
        "canonical": False,
        "production_qualified": False,
        "target_grating_run": False,
        "mpi_size": MPI.COMM_WORLD.size,
        "b1": b1,
        "b2": b2,
    }
