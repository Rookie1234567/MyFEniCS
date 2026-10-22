from __future__ import annotations

import json

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.dyadic_hexa_broken_mesh import (
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.exact_sequence_variable_p import (
    build_variable_p_reference_space,
)
from src.adaptivity.hcurl_broken_cell_trace import (
    build_broken_hexa_cell_trace_constraint_map,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    build_broken_hexa_entity_degree_arrays,
    build_broken_hexa_trace_constraint_authority,
)
from src.adaptivity.variable_p_degree_plan import (
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    weighted_vector_field_metrics,
)
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.solvers.common_3d_forms import _build_physical_volume_terms
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
)
from src.solvers.hcurl_blocked_gram_tensor import HcurlBlockedGramTensor
from src.solvers.hcurl_variable_p_assembly import (
    build_variable_p_condensed_trace_system,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_vector,
)
from src.solvers.hcurl_variable_p_local import project_p6_local_tensor


def _degree_for_box(box: tuple[float, ...], lower_degree: int) -> int:
    return lower_degree if float(box[0]) < 1.0 else lower_degree + 1


def _cell_box(msh, cell: int) -> tuple[float, float, float, float, float, float]:
    coordinates = np.asarray(
        msh.geometry.x[np.asarray(msh.geometry.dofmap[cell], dtype=np.int32), :3],
        dtype=np.float64,
    )
    return tuple(
        float(value)
        for value in np.round(
            (*np.min(coordinates, axis=0), *np.max(coordinates, axis=0)),
            decimals=12,
        )
    )


def _degree_array_for_broken_mesh(
    msh,
    degree_by_box: dict[tuple[float, ...], int],
) -> np.ndarray:
    cell_map = msh.topology.index_map(3)
    local_count = int(cell_map.size_local + cell_map.num_ghosts)
    return np.asarray(
        [
            degree_by_box[_cell_box(msh, cell)]
            for cell in range(local_count)
        ],
        dtype=np.int32,
    )


def _broken_mixed_p_fixture(comm: MPI.Intracomm, lower_degree: int):
    cfg = task43_initial_profile()
    forest = build_root_dyadic_hexa_forest(
        (
            (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
        ),
        (cfg.tags.grating, cfg.tags.grating),
        periodic_axes=(),
        protect_material_interfaces=False,
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        (DyadicHexKey(0, 0, 0, 0, 0),),
    )
    assert len(forest.leaves) == 9
    carrier = build_broken_dyadic_hexa_carrier(forest, comm=comm)
    msh = carrier.mesh
    degree_by_box = {
        cell.box: _degree_for_box(cell.box, lower_degree)
        for cell in forest.leaves
    }
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=lower_degree + 1,
        periodic_axes=(),
        cell_degree_by_box=degree_by_box,
    )
    closure = authority.audit["variable_trace_degree_audit"]
    assert closure["maximum_adjacent_or_periodic_cell_p_jump"] == 1
    assert closure["hanging_patch_degrees"] == [lower_degree]
    edge_degrees, face_degrees = build_broken_hexa_entity_degree_arrays(
        forest,
        carrier,
        authority,
    )
    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=_degree_array_for_broken_mesh(msh, degree_by_box),
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )
    assert constraints.audit["pass"] is True
    return cfg, forest, carrier, entity_map, constraints


def _conforming_12_cell_fixture(comm: MPI.Intracomm, cfg, lower_degree: int):
    x_axis = (0.0, 0.5, 1.0, 2.0)
    y_axis = (0.0, 0.5, 1.0)
    z_axis = (0.0, 0.5, 1.0)
    points = np.asarray(
        [
            (x, y, z)
            for z in z_axis
            for y in y_axis
            for x in x_axis
        ],
        dtype=default_real_type,
    )

    def point_id(i: int, j: int, k: int) -> int:
        return k * len(y_axis) * len(x_axis) + j * len(x_axis) + i

    cells: list[tuple[int, ...]] = []
    for k in range(len(z_axis) - 1):
        for j in range(len(y_axis) - 1):
            for i in range(len(x_axis) - 1):
                cells.append(
                    (
                        point_id(i, j, k),
                        point_id(i + 1, j, k),
                        point_id(i, j + 1, k),
                        point_id(i + 1, j + 1, k),
                        point_id(i, j, k + 1),
                        point_id(i + 1, j, k + 1),
                        point_id(i, j + 1, k + 1),
                        point_id(i + 1, j + 1, k + 1),
                    )
                )
    coordinate_element = ufl.Mesh(
        element(
            "Lagrange",
            "hexahedron",
            1,
            shape=(3,),
            dtype=default_real_type,
        )
    )
    msh = mesh.create_mesh(
        comm,
        np.asarray(cells, dtype=np.int64),
        coordinate_element,
        points,
    )
    n_cells = int(msh.topology.index_map(3).size_local)
    indices = np.arange(n_cells, dtype=np.int32)
    tags = mesh.meshtags(
        msh,
        3,
        indices,
        np.full(n_cells, int(cfg.tags.grating), dtype=np.int32),
    )
    boxes = cell_box_catalog(msh)
    degree_by_box = {
        box: _degree_for_box(box, lower_degree) for box in boxes
    }
    degree_plan = build_variable_p_cell_degree_plan(msh, degree_by_box)
    assert degree_plan.audit["cell_count"] == 12
    assert degree_plan.audit["maximum_adjacent_cell_degree_jump"] == 1
    assert degree_plan.audit["entity_degree_closure"] == (
        "face=min(incident cell); edge=min(incident cell)"
    )
    return msh, tags, degree_plan.entity_map


def _task43_p6_operator(msh, cell_tags, cfg):
    p6_space = fem.functionspace(msh, ("N1curl", 6))
    trial = ufl.TrialFunction(p6_space)
    test = ufl.TestFunction(p6_space)
    metadata = {
        "quadrature_degree": int(cfg.stage4_volume_quadrature_degree),
        "quadrature_rule": str(cfg.stage4_volume_quadrature_rule),
    }
    dx = ufl.Measure(
        "dx",
        domain=msh,
        subdomain_data=cell_tags,
        metadata=metadata,
    )
    curl_form, mass_form = _build_physical_volume_terms(
        cfg,
        trial,
        test,
        dx,
    )
    bilinear_form = curl_form + mass_form
    evaluator = HcurlBlockedGramTensor(
        p6_space.element.basix_element,
        cfg,
        bilinear_form,
    )
    return p6_space, bilinear_form, evaluator, metadata


def _p6_cell_tensors(msh, cfg, evaluator):
    cell_count = int(msh.topology.index_map(3).size_local)
    tensors: list[np.ndarray] = []
    tensor_keys: list[tuple[object, ...]] = []
    cache: dict[tuple[object, ...], np.ndarray] = {}
    for cell in range(cell_count):
        coordinates, widths = _canonical_axis_aligned_coordinates(
            msh,
            cell,
            tolerance=1.0e-12,
            geometry_identity_policy="raw_unrounded",
        )
        key = (int(cfg.tags.grating), *widths)
        tensor = cache.get(key)
        if tensor is None:
            tensor = evaluator.build(
                coordinates,
                tag=int(cfg.tags.grating),
                dimension=882,
            )
            cache[key] = tensor
        tensors.append(tensor)
        tensor_keys.append(key)
    return tuple(tensors), tuple(tensor_keys)


def _manufactured_field(msh, degree: int = 3):
    x = ufl.SpatialCoordinate(msh)
    s = x[0] / 2.0
    y, z = x[1], x[2]
    y_bubble = y * (1.0 - y)
    z_bubble = z * (1.0 - z)
    s_bubble = s * (1.0 - s)
    a, b, c, d, e, f = (
        fem.Constant(msh, PETSc.ScalarType(value))
        for value in (
            1.0 + 0.3j,
            -0.4 + 0.8j,
            0.6 - 0.5j,
            -0.7 + 0.2j,
            0.25 + 0.9j,
            0.5 - 0.6j,
        )
    )
    electric = ufl.as_vector(
        (
            a * y**degree * z**degree
            + d * s ** (degree - 1) * y_bubble * z_bubble,
            b * s**degree * z**degree
            + e * s_bubble * y ** (degree - 1) * z_bubble,
            c * s**degree * y**degree
            + f * s_bubble * y_bubble * z ** (degree - 1),
        )
    )
    return electric


def _manufactured_values_and_curl(
    points: np.ndarray,
    degree: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=np.float64)
    x, y, z = points.T
    s = x / 2.0
    yb = y * (1.0 - y)
    zb = z * (1.0 - z)
    sb = s * (1.0 - s)
    a, b, c, d, e, f = (
        1.0 + 0.3j,
        -0.4 + 0.8j,
        0.6 - 0.5j,
        -0.7 + 0.2j,
        0.25 + 0.9j,
        0.5 - 0.6j,
    )
    electric = np.column_stack(
        (
            a * y**degree * z**degree
            + d * s ** (degree - 1) * yb * zb,
            b * s**degree * z**degree
            + e * sb * y ** (degree - 1) * zb,
            c * s**degree * y**degree
            + f * sb * yb * z ** (degree - 1),
        )
    )
    d_ex_dy = (
        a * degree * y ** (degree - 1) * z**degree
        + d * s ** (degree - 1) * (1.0 - 2.0 * y) * zb
    )
    d_ex_dz = (
        a * degree * y**degree * z ** (degree - 1)
        + d * s ** (degree - 1) * yb * (1.0 - 2.0 * z)
    )
    d_ey_dz = (
        b * degree * s**degree * z ** (degree - 1)
        + e * sb * y ** (degree - 1) * (1.0 - 2.0 * z)
    )
    d_ey_dx = 0.5 * (
        b * degree * s ** (degree - 1) * z**degree
        + e * (1.0 - 2.0 * s) * y ** (degree - 1) * zb
    )
    d_ez_dy = (
        c * degree * s**degree * y ** (degree - 1)
        + f * sb * (1.0 - 2.0 * y) * z ** (degree - 1)
    )
    d_ez_dx = 0.5 * (
        c * degree * s ** (degree - 1) * y**degree
        + f * (1.0 - 2.0 * s) * yb * z ** (degree - 1)
    )
    curl = np.column_stack(
        (
            d_ez_dy - d_ey_dz,
            d_ex_dz - d_ez_dx,
            d_ey_dx - d_ex_dy,
        )
    )
    return electric, curl


def _assemble_cellwise_active_rhs(
    msh,
    p6_space,
    entity_map,
    cfg,
    exact_field,
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    metadata = {
        "quadrature_degree": int(cfg.stage4_volume_quadrature_degree),
        "quadrature_rule": str(cfg.stage4_volume_quadrature_rule),
    }
    test = ufl.TestFunction(p6_space)
    curl_coefficient = PETSc.ScalarType(1.0 / cfg.mu_r)
    mass_coefficient = PETSc.ScalarType(
        -cfg.k0**2 * cfg.grating_index**2
    )
    integrand = (
        curl_coefficient
        * ufl.inner(ufl.curl(exact_field), ufl.curl(test))
        + mass_coefficient * ufl.inner(exact_field, test)
    )
    active_rhs = np.zeros(entity_map.active_rows, dtype=np.complex128)
    rhs_by_cell: dict[int, np.ndarray] = {}
    for entity_cell in entity_map.owned_cells:
        local_cell = int(entity_cell.local_cell)
        cell_tag = mesh.meshtags(
            msh,
            3,
            np.asarray([local_cell], dtype=np.int32),
            np.asarray([1], dtype=np.int32),
        )
        dx = ufl.Measure(
            "dx",
            domain=msh,
            subdomain_data=cell_tag,
            metadata=metadata,
        )
        form = fem.form(integrand * dx(1))
        p6_rhs = fem.petsc.assemble_vector(form)
        p6_rhs.ghostUpdate(
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        p6_rhs.assemble()
        try:
            local_dofs = np.asarray(
                p6_space.dofmap.cell_dofs(local_cell),
                dtype=np.int32,
            )
            local_p6_rhs = np.asarray(
                p6_rhs.getArray(readonly=True)[local_dofs],
                dtype=np.complex128,
            ).copy()
        finally:
            p6_rhs.destroy()
        space = build_variable_p_reference_space(entity_cell.degree_map)
        local_active_rhs = space.project_p6_oriented_dual(
            local_p6_rhs,
            cell_info=entity_cell.cell_info,
        )
        rhs_by_cell[entity_cell.global_cell] = local_active_rhs
        local_trace_rhs = local_active_rhs[space.trace_dofs]
        np.add.at(active_rhs, entity_cell.trace_rows, local_trace_rhs)
        np.add.at(
            active_rhs,
            entity_cell.interior_rows,
            local_active_rhs[space.interior_dofs],
        )
    return active_rhs, rhs_by_cell


def _solve_and_audit(
    msh,
    entity_map,
    constraints,
    p6_tensors,
    tensor_keys,
    p6_space,
    cfg,
    exact_field,
):
    system = build_variable_p_condensed_trace_system(
        entity_map,
        p6_tensors,
        tensor_class_keys=tensor_keys,
        trace_constraints=constraints,
    )
    active_rhs, rhs_by_cell = _assemble_cellwise_active_rhs(
        msh,
        p6_space,
        entity_map,
        cfg,
        exact_field,
    )
    active_rhs_vec = PETSc.Vec().createMPI(
        (entity_map.active_rows, entity_map.active_rows),
        comm=msh.comm,
    )
    active_rhs_vec.getArray()[:] = active_rhs
    active_rhs_vec.assemble()
    trace_rhs = condense_variable_p_active_vector_to_trace(
        system,
        active_rhs_vec,
        side="right",
        relative_tolerance=0.0,
        absolute_tolerance=0.0,
    )
    trace_solution = system.matrix.createVecRight()
    solver = PETSc.KSP().create(comm=msh.comm)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.LU)
    solver.setOperators(system.matrix)
    solver.solve(trace_rhs, trace_solution)
    converged_reason = int(solver.getConvergedReason())
    if converged_reason <= 0:
        raise AssertionError(
            f"manufactured solve did not converge: reason={converged_reason}"
        )
    trace_values = np.asarray(
        trace_solution.getArray(readonly=True), dtype=np.complex128
    ).copy()
    action = trace_rhs.duplicate()
    system.matrix.mult(trace_solution, action)
    reduced_residual = np.asarray(
        action.getArray(readonly=True) - trace_rhs.getArray(readonly=True),
        dtype=np.complex128,
    )
    reduced_scale = max(
        float(np.linalg.norm(trace_rhs.getArray(readonly=True))),
        float(np.linalg.norm(action.getArray(readonly=True))),
        np.finfo(float).tiny,
    )
    reduced_relative = float(np.linalg.norm(reduced_residual) / reduced_scale)
    action.destroy()
    solver.destroy()

    local_recoveries = system.recover_owned_active_cells(
        trace_values,
        active_full_rhs=active_rhs_vec,
    )
    constraints_by_cell = (
        {}
        if constraints is None
        else {cell.global_cell: cell for cell in constraints.owned_cells}
    )
    raw_trace_rows = (
        entity_map.active_trace_rows
        if constraints is None
        else constraints.independent_trace_rows
    )
    raw_trace_residual = np.zeros(raw_trace_rows, dtype=np.complex128)
    raw_interior_residual = np.zeros(
        entity_map.active_cell_interior_rows,
        dtype=np.complex128,
    )
    raw_action_norm_sq = 0.0
    raw_rhs_norm_sq = 0.0
    for entity_cell, (_cell, local_active) in zip(
        entity_map.owned_cells,
        local_recoveries,
        strict=True,
    ):
        space = build_variable_p_reference_space(entity_cell.degree_map)
        tensor = p6_tensors[entity_cell.local_cell]
        active_tensor = project_p6_local_tensor(space, tensor)
        active_tensor = space.orient_hcurl_tensor(
            active_tensor,
            cell_info=entity_cell.cell_info,
        )
        local_action = active_tensor @ local_active
        local_rhs = rhs_by_cell[entity_cell.global_cell]
        local_residual = local_action - local_rhs
        raw_action_norm_sq += float(np.vdot(local_action, local_action).real)
        raw_rhs_norm_sq += float(np.vdot(local_rhs, local_rhs).real)
        local_trace_residual = local_residual[space.trace_dofs]
        constrained_cell = constraints_by_cell.get(entity_cell.global_cell)
        if constrained_cell is None:
            trace_rows = entity_cell.trace_rows
            trace_values_local = local_trace_residual
        else:
            trace_rows = constrained_cell.independent_rows
            trace_values_local = (
                constrained_cell.full_trace_from_independent.conj().T
                @ local_trace_residual
            )
        np.add.at(raw_trace_residual, trace_rows, trace_values_local)
        np.add.at(
            raw_interior_residual,
            entity_cell.interior_rows
            - entity_map.active_trace_rows,
            local_residual[space.interior_dofs],
        )
    raw_trace_norm = float(np.linalg.norm(raw_trace_residual))
    raw_interior_norm = float(np.linalg.norm(raw_interior_residual))
    raw_relative = float(
        np.hypot(raw_trace_norm, raw_interior_norm)
        / max(
            np.sqrt(raw_action_norm_sq),
            np.sqrt(raw_rhs_norm_sq),
            np.finfo(float).tiny,
        )
    )
    full_active = recover_variable_p_active_full_vector(
        system,
        trace_values,
        active_full_rhs=active_rhs_vec,
    )
    recovered_field = fem.Function(p6_space)
    field_values = recovered_field.x.array
    local_coefficients_by_dof: dict[int, complex] = {}
    for entity_cell, local_active in local_recoveries:
        space = build_variable_p_reference_space(entity_cell.degree_map)
        local_p6 = space.active_to_p6_oriented(
            local_active,
            cell_info=entity_cell.cell_info,
        )
        dofs = np.asarray(
            p6_space.dofmap.cell_dofs(entity_cell.local_cell),
            dtype=np.int32,
        )
        for dof, value in zip(dofs, local_p6, strict=True):
            previous = local_coefficients_by_dof.get(int(dof))
            if previous is not None and not np.isclose(
                previous,
                value,
                rtol=2.0e-9,
                atol=2.0e-10,
            ):
                raise AssertionError(
                    "recovered p6 coefficients disagree on a shared mesh entity"
                )
            local_coefficients_by_dof[int(dof)] = complex(value)
    for dof, value in local_coefficients_by_dof.items():
        field_values[dof] = PETSc.ScalarType(value)
    recovered_field.x.scatter_forward()
    result = {
        "system": system,
        "active_rhs_vec": active_rhs_vec,
        "trace_rhs": trace_rhs,
        "trace_solution": trace_solution,
        "trace_values": trace_values,
        "full_active": full_active,
        "field": recovered_field,
        "reduced_residual": reduced_relative,
        "solver_converged_reason": converged_reason,
        "raw_trace_residual": raw_trace_norm,
        "raw_interior_residual": raw_interior_norm,
        "raw_full_active_residual": raw_relative,
        "active_trace_rows": int(system.active_trace_rows),
        "active_full_rows": int(entity_map.active_rows),
        "independent_active_rows": int(raw_trace_rows + entity_map.active_cell_interior_rows),
        "exact_field": exact_field,
    }
    return result


def _destroy_result(result) -> None:
    for name in (
        "full_active",
        "trace_solution",
        "trace_rhs",
        "active_rhs_vec",
    ):
        vector = result.get(name)
        if vector is not None:
            vector.destroy()
    system = result.get("system")
    if system is not None:
        system.destroy()


def _mesh_axes(boxes):
    return tuple(
        np.unique(
            np.asarray(
                [value for box in boxes for value in (box[axis], box[axis + 3])],
                dtype=np.float64,
            )
        )
        for axis in range(3)
    )


@pytest.mark.parametrize("lower_degree", (3, 4), ids=("p3_p4", "p4_p5"))
@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="the manufactured 9-to-12 mixed-p fixtures are serial-only",
)
def test_task43_mixed_p_hanging_9_to_12_manufactured_solve(
    lower_degree: int,
) -> None:
    comm = MPI.COMM_WORLD
    higher_degree = lower_degree + 1
    cfg, forest, carrier, broken_entity_map, constraints = (
        _broken_mixed_p_fixture(comm, lower_degree)
    )
    broken_mesh = carrier.mesh
    conforming_mesh, conforming_tags, conforming_entity_map = (
        _conforming_12_cell_fixture(comm, cfg, lower_degree)
    )
    broken_p6_space, _broken_form, evaluator, metadata = _task43_p6_operator(
        broken_mesh,
        carrier.cell_tags,
        cfg,
    )
    assert metadata["quadrature_degree"] == 15
    assert metadata["quadrature_rule"] == "default"
    assert constraints.audit["pass"] is True
    assert len(forest.hanging_faces) == 1

    broken_tensors, broken_tensor_keys = _p6_cell_tensors(
        broken_mesh,
        cfg,
        evaluator,
    )
    conforming_p6_space, _form12, conforming_evaluator, _metadata12 = (
        _task43_p6_operator(conforming_mesh, conforming_tags, cfg)
    )
    conforming_tensors, conforming_tensor_keys = _p6_cell_tensors(
        conforming_mesh,
        cfg,
        conforming_evaluator,
    )
    assert len(broken_tensors) == 9
    assert len(conforming_tensors) == 12
    assert all(tensor.shape == (882, 882) for tensor in broken_tensors)

    exact_broken = _manufactured_field(broken_mesh, degree=lower_degree)
    exact_conforming = _manufactured_field(
        conforming_mesh,
        degree=lower_degree,
    )
    broken_result = _solve_and_audit(
        broken_mesh,
        broken_entity_map,
        constraints,
        broken_tensors,
        broken_tensor_keys,
        broken_p6_space,
        cfg,
        exact_broken,
    )
    conforming_result = _solve_and_audit(
        conforming_mesh,
        conforming_entity_map,
        None,
        conforming_tensors,
        conforming_tensor_keys,
        conforming_p6_space,
        cfg,
        exact_conforming,
    )
    try:
        assert broken_result["reduced_residual"] <= 1.0e-9
        assert conforming_result["reduced_residual"] <= 1.0e-9
        assert broken_result["solver_converged_reason"] > 0
        assert conforming_result["solver_converged_reason"] > 0
        assert broken_result["raw_full_active_residual"] <= 1.0e-9
        assert conforming_result["raw_full_active_residual"] <= 1.0e-9
        assert broken_result["active_trace_rows"] == int(
            constraints.independent_trace_rows
        )
        assert conforming_result["active_trace_rows"] == (
            conforming_entity_map.active_trace_rows
        )

        broken_export = prepare_cell_local_vector_field_export(
            broken_result["field"]
        )
        conforming_export = prepare_cell_local_vector_field_export(
            conforming_result["field"]
        )
        broken_boxes = tuple(cell.box for cell in forest.leaves)
        conforming_boxes = cell_box_catalog(conforming_mesh)
        quadrature = build_common_volume_quadrature(
            (
                _mesh_axes(broken_boxes),
                _mesh_axes(conforming_boxes),
            ),
            gauss_order=8,
        )
        broken_samples = sample_cell_local_vector_fields(
            {
                "electric": broken_export.electric_dgq6,
                "curl_electric": broken_export.curl_electric_dgq6,
            },
            quadrature.points_nm,
        )
        conforming_samples = sample_cell_local_vector_fields(
            {
                "electric": conforming_export.electric_dgq6,
                "curl_electric": conforming_export.curl_electric_dgq6,
            },
            quadrature.points_nm,
        )
        exact_electric, exact_curl = _manufactured_values_and_curl(
            quadrature.points_nm,
            degree=lower_degree,
        )
        assert broken_samples is not None
        assert conforming_samples is not None
        broken_electric_error = weighted_vector_field_metrics(
            exact_electric,
            broken_samples["electric"],
            quadrature.weights_nm3,
        )
        conforming_electric_error = weighted_vector_field_metrics(
            exact_electric,
            conforming_samples["electric"],
            quadrature.weights_nm3,
        )
        broken_curl_error = weighted_vector_field_metrics(
            exact_curl,
            broken_samples["curl_electric"],
            quadrature.weights_nm3,
        )
        conforming_curl_error = weighted_vector_field_metrics(
            exact_curl,
            conforming_samples["curl_electric"],
            quadrature.weights_nm3,
        )
        field_cross = weighted_vector_field_metrics(
            conforming_samples["electric"],
            broken_samples["electric"],
            quadrature.weights_nm3,
        )
        curl_cross = weighted_vector_field_metrics(
            conforming_samples["curl_electric"],
            broken_samples["curl_electric"],
            quadrature.weights_nm3,
        )
        for metrics in (
            broken_electric_error,
            conforming_electric_error,
            broken_curl_error,
            conforming_curl_error,
            field_cross,
            curl_cross,
        ):
            assert metrics["relative_to_reference"] is not None
            assert float(metrics["relative_to_reference"]) <= 1.0e-8
        assert broken_result["independent_active_rows"] == (
            broken_result["active_trace_rows"]
            + broken_entity_map.active_cell_interior_rows
        )
        assert conforming_result["independent_active_rows"] == (
            conforming_entity_map.active_trace_rows
            + conforming_entity_map.active_cell_interior_rows
        )
        metrics_record = {
            "lower_degree": lower_degree,
            "higher_degree": higher_degree,
            "broken": {
                "independent_active_rows": broken_result[
                    "independent_active_rows"
                ],
                "solver_converged_reason": broken_result[
                    "solver_converged_reason"
                ],
                "reduced_relative_residual": broken_result[
                    "reduced_residual"
                ],
                "independent_full_action_relative_residual": broken_result[
                    "raw_full_active_residual"
                ],
                "independent_trace_residual_l2": broken_result[
                    "raw_trace_residual"
                ],
                "independent_interior_residual_l2": broken_result[
                    "raw_interior_residual"
                ],
                "electric_vs_manufactured": broken_electric_error,
                "curl_vs_manufactured": broken_curl_error,
            },
            "conforming": {
                "independent_active_rows": conforming_result[
                    "independent_active_rows"
                ],
                "solver_converged_reason": conforming_result[
                    "solver_converged_reason"
                ],
                "reduced_relative_residual": conforming_result[
                    "reduced_residual"
                ],
                "independent_full_action_relative_residual": (
                    conforming_result["raw_full_active_residual"]
                ),
                "independent_trace_residual_l2": conforming_result[
                    "raw_trace_residual"
                ],
                "independent_interior_residual_l2": conforming_result[
                    "raw_interior_residual"
                ],
                "electric_vs_manufactured": conforming_electric_error,
                "curl_vs_manufactured": conforming_curl_error,
            },
            "broken_vs_conforming": {
                "electric": field_cross,
                "curl_electric": curl_cross,
            },
            "common_quadrature_sha256": quadrature.rule_sha256,
            "comparison_space_note": (
                "The 9-leaf hanging mesh and 12-cell conforming mesh have "
                "different FE spaces and independent DoF counts; comparison "
                "uses a shared manufactured field and common physical integral."
            ),
        }
        print(
            "TASK43_MIXED_HP_9_TO_12 "
            + json.dumps(metrics_record, sort_keys=True, allow_nan=False),
            flush=True,
        )
    finally:
        _destroy_result(broken_result)
        _destroy_result(conforming_result)
