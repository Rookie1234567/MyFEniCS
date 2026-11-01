from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.swept_hex_mesh import build_swept_hex_mesh
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
    condense_unconstrained_vector_to_active_trace,
    recover_owned_cell_interiors,
)
from src.solvers.hcurl_cell_static_condensation import (
    build_explicit_cell_static_condensation,
    build_floquet_independent_trace_system,
    owned_hcurl_cell_interior_dofs,
)


def _small_gate_cd_swept_fixture():
    # Eight cells: 2 x 2 x 2. Periodic outer faces stay at fixed x/y planes;
    # internal x/y lines move with z to produce genuine Q1 mapped cells.
    z = np.asarray((-10.0, 0.0, 130.0), dtype=np.float64)
    x = np.asarray(((0.0, 25.0, 50.0), (0.0, 23.5, 50.0), (0.0, 22.0, 50.0)))
    y = np.asarray(((0.0, 12.5, 25.0), (0.0, 13.0, 25.0), (0.0, 13.5, 25.0)))
    msh, _ = build_swept_hex_mesh(
        MPI.COMM_SELF,
        z,
        x,
        y,
        require_periodic_xy=True,
    )
    tdim = msh.topology.dim
    facets_by_tag = []
    for axis, value, tag in (
        (0, 0.0, 11),
        (0, 50.0, 12),
        (1, 0.0, 13),
        (1, 25.0, 14),
    ):
        facets = mesh.locate_entities_boundary(
            msh,
            tdim - 1,
            lambda points, axis=axis, value=value: np.isclose(
                points[axis], value, rtol=0.0, atol=1.0e-11
            ),
        )
        facets_by_tag.extend((int(facet), int(tag)) for facet in facets)
    facet_to_tag = dict(facets_by_tag)
    facets = np.asarray(sorted(facet_to_tag), dtype=np.int32)
    values = np.asarray([facet_to_tag[int(facet)] for facet in facets], dtype=np.int32)
    facet_tags = mesh.meshtags(msh, tdim - 1, facets, values)
    cell_count = int(msh.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        msh,
        tdim,
        np.arange(cell_count, dtype=np.int32),
        np.ones(cell_count, dtype=np.int32),
    )
    cfg = target_stage4_config(degree=6, h_nm=25.0)
    cfg.incident_theta_deg = 23.0
    cfg.incident_phi_deg = 31.0
    cfg.floquet_constraint_mode = "auto"
    # These are stored configuration values; x/y properties resolve to 0..period.
    cfg.z_min = -10.0
    cfg.z_max = 130.0
    cfg.period_x = 50.0
    cfg.period_y = 25.0
    mesh_data = SimpleNamespace(mesh=msh, facet_tags=facet_tags)
    return msh, cell_tags, mesh_data, cfg


def _relative_matrix_difference(first, second) -> float:
    difference = first.copy()
    try:
        difference.axpy(
            PETSc.ScalarType(-1.0),
            second,
            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
        )
        return float(difference.norm() / max(float(second.norm()), 1.0e-30))
    finally:
        difference.destroy()


def _write_validation_report(report: dict[str, object]) -> None:
    payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    print(payload, end="", flush=True)
    report_path = os.environ.get("TASK40_GATE_CD_VALIDATION_REPORT")
    if report_path:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def _compile_form(V, cell_tags, quadrature_degree: int):
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure(
        "dx",
        domain=V.mesh,
        subdomain_data=cell_tags,
        metadata={"quadrature_degree": int(quadrature_degree)},
    )
    # Complex lossy mass and curl terms; constant coefficients are embedded in
    # the kernel so the cell-tensor condensation contract is met.
    return fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.2 - 0.13j) * ufl.inner(u, v)
        )
        * dx(1)
    )


def test_mapped_p6_condensation_matches_independent_full_assembly_and_recovery():
    msh, cell_tags, mesh_data, cfg = _small_gate_cd_swept_fixture()
    V = fem.functionspace(
        msh,
        element("N1curl", "hexahedron", 6, dtype=default_real_type),
    )
    floquet = build_double_floquet_mpc(V, mesh_data, cfg)
    assert abs(floquet.phase_x - 1.0) > 1.0e-3
    assert abs(floquet.phase_y - 1.0) > 1.0e-3
    assert floquet.num_x_constraints > 0
    assert floquet.num_y_constraints > 0
    assert floquet.max_face_pairing_coordinate_error < 1.0e-10
    assert int(msh.topology.index_map(msh.topology.dim).size_local) == 8

    q15 = _compile_form(V, cell_tags, 15)
    q21 = _compile_form(V, cell_tags, 21)
    q27 = _compile_form(V, cell_tags, 27)
    system15 = system21 = system27 = None
    full15 = embedded15 = rhs_embedded = post = independent = None
    zero_rhs = None
    rhs_full = rhs_condensed = action = reconstructed_action = residual = None
    active_vector = None
    exact = reconstructed = None
    try:
        system15 = build_unconstrained_assembly_time_condensation(
            q15,
            V,
            cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
            geometry_identity_policy="mapped_exact",
            mapped_geometry_translation_invariant=False,
        )
        system21 = build_unconstrained_assembly_time_condensation(
            q21,
            V,
            cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
            geometry_identity_policy="mapped_exact",
            mapped_geometry_translation_invariant=False,
        )
        system27 = build_unconstrained_assembly_time_condensation(
            q27,
            V,
            cell_tags,
            mpc=floquet.mpc,
            materialize_global_matrix=True,
            geometry_identity_policy="mapped_exact",
            mapped_geometry_translation_invariant=False,
        )
        assert system15.matrix is not None
        assert system21.matrix is not None
        assert system27.matrix is not None
        quadrature_15_21 = _relative_matrix_difference(
            system15.matrix, system21.matrix
        )
        quadrature_21_27 = _relative_matrix_difference(
            system21.matrix, system27.matrix
        )

        full15 = fem_petsc.assemble_matrix(q15, bcs=[])
        full15.assemble()
        embedded15 = dolfinx_mpc.assemble_matrix(q15, floquet.mpc, bcs=[])
        embedded15.assemble()
        zero_rhs = embedded15.createVecRight()
        zero_rhs.set(PETSc.ScalarType(0.0))
        zero_rhs.assemble()
        interiors = owned_hcurl_cell_interior_dofs(V)
        post = build_explicit_cell_static_condensation(
            embedded15,
            zero_rhs,
            interiors,
        )
        slave_local = np.asarray(floquet.mpc.slaves, dtype=np.int64)
        index_map = V.dofmap.index_map
        if int(index_map.num_ghosts) != 0:
            raise AssertionError("COMM_SELF fixture unexpectedly has ghost DoFs")
        slave_global = index_map.local_to_global(slave_local.astype(np.int32))
        independent = build_floquet_independent_trace_system(
            post.matrix,
            post.rhs,
            owned_slave_original_dofs=slave_global,
            original_to_trace=post.original_to_trace,
        )
        condensed_matrix_error = _relative_matrix_difference(
            system15.matrix, independent.matrix
        )

        rng = np.random.default_rng(20261101)
        exact = fem.Function(V)
        exact.x.array[:] = (
            rng.standard_normal(len(exact.x.array))
            + 1j * rng.standard_normal(len(exact.x.array))
        ).astype(PETSc.ScalarType)
        exact.x.array[slave_local] = 0.0
        exact.x.scatter_forward()
        floquet.mpc.backsubstitution(exact)
        exact.x.scatter_forward()
        rhs_full = full15.createVecRight()
        full15.mult(exact.x.petsc_vec, rhs_full)
        interiors_all = np.concatenate(interiors)
        interior_rhs_norm = float(
            np.linalg.norm(rhs_full.getValues(interiors_all))
        )
        if not np.isfinite(interior_rhs_norm) or interior_rhs_norm <= 0.0:
            raise AssertionError("manufactured full RHS has no interior component")

        rhs_condensed = condense_unconstrained_vector_to_active_trace(
            system15,
            rhs_full,
            side="right",
            relative_tolerance=0.0,
        )
        active_values = np.zeros(system15.active_rows, dtype=np.complex128)
        for original, active_id in system15.trace_constraints.original_to_active.items():
            active_values[int(active_id)] = exact.x.array[int(original)]
        if float(np.linalg.norm(active_values)) <= 0.0:
            raise AssertionError("manufactured field has no nonzero active trace")
        for original, (active_ids, coefficients) in (
            system15.trace_constraints.expansion_by_original.items()
        ):
            predicted = np.dot(coefficients, active_values[active_ids])
            if abs(predicted - exact.x.array[int(original)]) > 2.0e-11 * max(
                1.0, abs(exact.x.array[int(original)])
            ):
                raise AssertionError("actual Bloch MPC backsubstitution disagrees with trace map")

        action = system15.matrix.createVecLeft()
        active_vector = system15.create_active_vector()
        active_vector.getArray()[:] = active_values
        active_vector.assemble()
        system15.matrix.mult(active_vector, action)
        action.axpy(PETSc.ScalarType(-1.0), rhs_condensed)
        reduced_residual = float(action.norm() / max(rhs_condensed.norm(), 1.0e-30))

        recovered_cells = recover_owned_cell_interiors(
            system15,
            active_values,
            full_rhs=rhs_full,
        )
        reconstructed = fem.Function(V)
        reconstructed.x.array[:] = 0.0
        for original, (active_ids, coefficients) in (
            system15.trace_constraints.expansion_by_original.items()
        ):
            reconstructed.x.array[int(original)] = np.dot(
                coefficients, active_values[active_ids]
            )
        for dofs, values in recovered_cells:
            reconstructed.x.array[np.asarray(dofs, dtype=np.int64)] = values
        reconstructed.x.scatter_forward()
        field_error = float(
            np.linalg.norm(reconstructed.x.array - exact.x.array)
            / max(np.linalg.norm(exact.x.array), 1.0e-30)
        )
        reconstructed_action = full15.createVecRight()
        full15.mult(reconstructed.x.petsc_vec, reconstructed_action)
        residual = reconstructed_action.copy()
        residual.axpy(PETSc.ScalarType(-1.0), rhs_full)
        full_residual = float(residual.norm() / max(rhs_full.norm(), 1.0e-30))

        rhs_embedded = embedded15.createVecRight()
        embedded15.mult(exact.x.petsc_vec, rhs_embedded)
        rhs_embedded.setValues(
            slave_global.astype(PETSc.IntType),
            np.zeros(len(slave_global), dtype=PETSc.ScalarType),
        )
        rhs_embedded.assemble()
        post_nonzero = build_explicit_cell_static_condensation(
            embedded15,
            rhs_embedded,
            interiors,
        )
        try:
            independent_nonzero = build_floquet_independent_trace_system(
                post_nonzero.matrix,
                post_nonzero.rhs,
                owned_slave_original_dofs=slave_global,
                original_to_trace=post_nonzero.original_to_trace,
            )
            try:
                rhs_difference = rhs_condensed.copy()
                rhs_difference.axpy(PETSc.ScalarType(-1.0), independent_nonzero.rhs)
                rhs_reference_error = float(
                    rhs_difference.norm()
                    / max(independent_nonzero.rhs.norm(), 1.0e-30)
                )
                rhs_difference.destroy()
            finally:
                independent_nonzero.destroy()
        finally:
            post_nonzero.destroy()

        _write_validation_report(
            {
                "cells": 8,
                "p": 6,
                "material_cell_tags": [1],
                "geometry": "separable z-swept first-order Q1 hex",
                "floquet_phase_x": [floquet.phase_x.real, floquet.phase_x.imag],
                "floquet_phase_y": [floquet.phase_y.real, floquet.phase_y.imag],
                "floquet_constraints_x": int(floquet.num_x_constraints),
                "floquet_constraints_y": int(floquet.num_y_constraints),
                "periodic_pairing_coordinate_error": float(
                    floquet.max_face_pairing_coordinate_error
                ),
                "condensed_vs_independent_matrix_relative": condensed_matrix_error,
                "full_global_dofs": int(system15.full_rows),
                "full_trace_dofs": int(system15.trace_rows),
                "active_trace_dofs_after_mpc": int(system15.active_rows),
                "cell_interior_dofs_global": int(system15.interior_rows),
                "nonzero_interior_rhs_norm": interior_rhs_norm,
                "schur_rhs_residual_relative": reduced_residual,
                "recovered_field_relative_error": field_error,
                "full_operator_residual_relative": full_residual,
                "nonzero_rhs_condensed_reference_relative": rhs_reference_error,
                "q15_vs_q21_schur_relative": quadrature_15_21,
                "q21_vs_q27_schur_relative": quadrature_21_27,
                "quadrature_interpretation": (
                    "diagnostic only; no q15 sufficiency gate is claimed"
                ),
                "mapped_cells": system15.build_audit["mapped_hex_cell_count_global"],
                "mapped_min_detJ": system15.build_audit["mapped_hex_detJ_analytic_min"],
            }
        )
        assert condensed_matrix_error < 2.0e-10
        assert reduced_residual < 2.0e-10
        assert field_error < 2.0e-10
        assert full_residual < 2.0e-10
        assert rhs_reference_error < 2.0e-10
        for quadrature_error in (quadrature_15_21, quadrature_21_27):
            assert np.isfinite(quadrature_error)
            assert quadrature_error >= 0.0
    finally:
        for obj in (
            residual,
            reconstructed_action,
            action,
            rhs_condensed,
            rhs_embedded,
            rhs_full,
            zero_rhs,
            active_vector,
        ):
            if obj is not None:
                obj.destroy()
        for obj in (independent,):
            if obj is not None:
                obj.destroy()
        for obj in (post,):
            if obj is not None:
                obj.destroy()
        for obj in (embedded15, full15):
            if obj is not None:
                obj.destroy()
        for obj in (system27, system21, system15):
            if obj is not None:
                obj.destroy()
        if floquet is not None:
            floquet.mpc.destroy()
