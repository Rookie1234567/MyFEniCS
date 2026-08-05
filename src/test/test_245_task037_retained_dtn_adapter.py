from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from dolfinx import mesh
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.dtn_port_3d as dtn_port_3d
from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.geometry.mesh_builder_3d import (
    AirBox3DMesh,
    _mark_boundary_facets,
    _mark_cells,
)
from src.solvers.common_3d_case_flow import run_prepared_3d_case_flow
from src.solvers.dtn_port_3d import Stage4ExternalLinearSolverSnapshot
from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
)


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    packets = comm.allgather(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    )
    return np.concatenate(packets) if packets else np.empty(0, dtype=np.complex128)


def _allreduce_dense(local: np.ndarray, comm: MPI.Intracomm) -> np.ndarray:
    result = np.zeros_like(local)
    comm.Allreduce(local, result, op=MPI.SUM)
    return result


def _relative(observed: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(observed) - np.asarray(expected))
        / max(float(np.linalg.norm(expected)), 1.0e-30)
    )


def _dense_action_solution(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
) -> tuple[PETSc.Vec, float, np.ndarray, np.ndarray, np.ndarray]:
    comm = operator.getComm().tompi4py()
    size = int(operator.getSize()[0])
    start, end = map(int, rhs.getOwnershipRange())
    source = rhs.duplicate()
    target = rhs.duplicate()
    local_dense = np.empty((end - start, size), dtype=np.complex128)
    for column in range(size):
        source.set(0.0)
        if start <= column < end:
            source.getArray()[column - start] = 1.0
        source.assemble()
        operator.mult(source, target)
        local_dense[:, column] = target.getArray(readonly=True)
    dense = np.vstack(comm.allgather(local_dense))
    global_rhs = np.concatenate(
        comm.allgather(
            np.asarray(rhs.getArray(readonly=True), dtype=np.complex128)
        )
    )
    solution = np.linalg.solve(dense, global_rhs)
    result = rhs.duplicate()
    result.getArray()[:] = solution[start:end]
    result.assemble()
    residual = rhs.duplicate()
    operator.mult(result, residual)
    residual.axpy(PETSc.ScalarType(-1.0), rhs)
    relative = float(residual.norm() / max(float(rhs.norm()), 1.0e-30))
    source.destroy()
    target.destroy()
    residual.destroy()
    return result, relative, dense, solution, global_rhs


def _dense_retained_matrix(system, comm: MPI.Intracomm) -> np.ndarray:
    rows = int(system.retained_rows)
    local = np.zeros((rows, rows), dtype=np.complex128)
    for cell in system.cells:
        ids, block = cell.contribution()
        local[np.ix_(ids, ids)] += block
    return _allreduce_dense(local, comm)


def _dense_matrix_free_dtn(
    blocks,
    entries,
    comm: MPI.Intracomm,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_fe = int(blocks.n_fe)
    n_aux = int(blocks.n_aux)
    local_c = np.zeros((n_fe, n_aux), dtype=np.complex128)
    local_d = np.zeros((n_aux, n_fe), dtype=np.complex128)
    for mode, rows, traction_values, cols, ell_values in entries:
        local_c[np.asarray(rows, dtype=np.int64), int(mode)] += traction_values
        local_d[int(mode), np.asarray(cols, dtype=np.int64)] += ell_values
    c = _allreduce_dense(local_c, comm)
    d = _allreduce_dense(local_d, comm)
    diagonal = blocks.H.getDiagonal()
    h = np.diag(_global_values(diagonal))
    diagonal.destroy()
    return c, d, h


def _tiny_target_mesh(cfg, comm: MPI.Intracomm) -> AirBox3DMesh:
    points = (
        np.asarray((cfg.x_min, cfg.y_min, cfg.domain_z_min), dtype=np.float64),
        np.asarray((cfg.x_max, cfg.y_max, cfg.domain_z_max), dtype=np.float64),
    )
    msh = mesh.create_box(
        comm,
        points,
        (2, 1, 1),
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    msh.name = cfg.case_name
    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    cell_tags = _mark_cells(msh, cfg)
    facet_tags, boundary_facets = _mark_boundary_facets(msh, cfg)
    return AirBox3DMesh(
        mesh=msh,
        cell_tags=cell_tags,
        facet_tags=facet_tags,
        boundary_facets=boundary_facets,
        mesh_cell_type_resolved="hexahedron",
        mesh_cells_resolved=(2, 1, 1),
        z_alignment_warnings=[],
        mesh_spacing_mode_resolved="uniform_strict_test_override",
        mesh_axis_cell_stats={},
        material_plane_alignment={"all_aligned": True},
        local_refinement_regions={"x": [], "y": [], "z": []},
    )


def _assert_mpc_backsubstitution(field, floquet_data) -> int:
    mpc = floquet_data.mpc
    index_map = field.function_space.dofmap.index_map
    owned_local = np.arange(int(index_map.size_local), dtype=np.int32)
    owned_global = np.asarray(index_map.local_to_global(owned_local), dtype=np.int64)
    owned_values = np.asarray(field.x.array[: owned_local.size]).copy()
    packets = field.function_space.mesh.comm.allgather(
        (owned_global, owned_values)
    )
    values_by_global = {
        int(global_id): complex(value)
        for packet_global, packet_values in packets
        for global_id, value in zip(packet_global, packet_values, strict=True)
    }
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    checked = 0
    for local_slave in np.unique(np.asarray(mpc.slaves, dtype=np.int64)):
        if local_slave < 0 or local_slave >= int(index_map.size_local):
            continue
        slave_global = int(index_map.local_to_global(np.asarray([local_slave], dtype=np.int32))[0])
        masters_local = np.asarray(mpc.masters.links(int(local_slave)), dtype=np.int32)
        start = int(offsets[int(local_slave)])
        stop = int(offsets[int(local_slave) + 1])
        masters_global = np.asarray(index_map.local_to_global(masters_local), dtype=np.int64)
        expected = np.dot(
            coefficients[start:stop],
            np.asarray(
                [values_by_global[int(value)] for value in masters_global],
                dtype=np.complex128,
            ),
        )
        assert abs(values_by_global[slave_global] - expected) <= 1.0e-11
        checked += 1
    return checked


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="R7b2b1 compiled-form retained DtN adapter uses serial or MPI2",
)
def test_retained_public_dtn_path_and_recovery(monkeypatch, tmp_path):
    comm = MPI.COMM_WORLD
    cfg = replace(
        target_stage4_config(degree=6, h_nm=100.0),
        case_name=f"task037_r7b2b1_tiny_p6_mpi{comm.size}",
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        diffraction_zero_order_only=True,
        stage4_dtn_order_policy="zero_order",
        direct_release_solver_before_postprocess=True,
        unique_output=False,
    )
    mesh_data = _tiny_target_mesh(cfg, comm)
    captured: dict[str, object] = {}

    original_effective_rhs = dtn_port_3d._retained_effective_recovery_rhs

    def observe_effective_rhs(external_rhs, modes, auxiliary_values, assemblers, config):
        effective = original_effective_rhs(
            external_rhs,
            modes,
            auxiliary_values,
            assemblers,
            config,
        )
        delta = effective.copy()
        delta.axpy(PETSc.ScalarType(-1.0), external_rhs)
        system = captured["request"].static_condensed_system
        interior_sq = 0.0
        complement_sq = 0.0
        for cell in system.cells:
            rows = np.asarray(
                cell.cell_original_dofs[cell.factor.p6_interior_dofs],
                dtype=PETSc.IntType,
            )
            values = np.asarray(delta.getValues(rows), dtype=np.complex128)
            interior_sq += float(np.vdot(values, values).real)
            complement = cell.factor.eliminated_basis.conj().T @ values
            complement_sq += float(np.vdot(complement, complement).real)
        full_delta_norm = float(delta.norm())
        global_interior_norm = float(
            np.sqrt(comm.allreduce(interior_sq, op=MPI.SUM))
        )
        core_sq = 0.0
        for cell in system.cells:
            rows = np.asarray(
                cell.cell_original_dofs[cell.factor.p6_interior_dofs],
                dtype=PETSc.IntType,
            )
            values = np.asarray(delta.getValues(rows), dtype=np.complex128)
            core = cell.factor.core_basis.conj().T @ values
            core_sq += float(np.vdot(core, core).real)
        captured["effective_rhs_delta_norm"] = full_delta_norm
        captured["effective_rhs_delta_interior_norm"] = global_interior_norm
        captured["effective_rhs_delta_core_norm"] = float(
            np.sqrt(comm.allreduce(core_sq, op=MPI.SUM))
        )
        captured["effective_rhs_delta_trace_norm"] = float(
            np.sqrt(max(full_delta_norm**2 - global_interior_norm**2, 0.0))
        )
        captured["effective_rhs_delta_complement_norm"] = float(
            np.sqrt(comm.allreduce(complement_sq, op=MPI.SUM))
        )
        captured["effective_rhs_delta_interior_relative"] = (
            captured["effective_rhs_delta_interior_norm"]
            / max(full_delta_norm, 1.0e-30)
        )
        captured["effective_rhs_delta_core_relative"] = (
            captured["effective_rhs_delta_core_norm"]
            / max(full_delta_norm, 1.0e-30)
        )
        captured["effective_rhs_delta_complement_relative"] = (
            captured["effective_rhs_delta_complement_norm"]
            / max(full_delta_norm, 1.0e-30)
        )
        captured["effective_rhs"] = effective.copy()
        delta.destroy()
        return effective

    def solve_request(request):
        captured["request"] = request
        system = request.static_condensed_system
        assert not isinstance(system, AssemblyTimeCondensedSystem)
        assert request.blocks.F is None
        assert request.blocks.C.getType() == PETSc.Mat.Type.PYTHON
        assert request.blocks.D.getType() == PETSc.Mat.Type.PYTHON
        c_context = request.blocks.C.getPythonContext()
        d_context = request.blocks.D.getPythonContext()
        assert c_context.state is d_context.state
        entries = c_context.state.entries
        assert request.n_fe == system.retained_rows
        assert request.b.getSize() == request.n_fe + request.n_aux
        assert request.blocks.b_fe.norm() > 1.0e-13
        retained_dense = _dense_retained_matrix(system, comm)
        c_dense, d_dense, h_dense = _dense_matrix_free_dtn(
            request.blocks,
            entries,
            comm,
        )
        core_ids = np.concatenate(
            tuple(
                cell.retained_global_ids[-108:]
                for cell in system.cells
            )
        )
        core_mask = np.zeros(system.retained_rows, dtype=bool)
        core_mask[core_ids] = True
        dtn_scale = max(
            float(np.linalg.norm(retained_dense)),
            float(np.linalg.norm(c_dense)),
            float(np.linalg.norm(d_dense)),
            1.0,
        )
        assert float(np.linalg.norm(c_dense[core_mask, :])) / dtn_scale <= 1.0e-11
        assert float(np.linalg.norm(d_dense[:, core_mask])) / dtn_scale <= 1.0e-11
        assert all(
            not set(entry[1]).intersection(set(core_ids))
            and not set(entry[3]).intersection(set(core_ids))
            for entry in entries
        )
        augmented_dense = np.block(
            [
                [retained_dense, c_dense],
                [d_dense, h_dense],
            ]
        )
        probe_values = np.sin(0.017 * np.arange(request.n_fe + request.n_aux)) + 1j * np.cos(
            0.023 * (np.arange(request.n_fe + request.n_aux) + 1)
        )
        probe = request.b.duplicate()
        start, end = map(int, probe.getOwnershipRange())
        probe.getArray()[:] = probe_values[start:end]
        probe.assemble()
        observed = request.operator.createVecRight()
        observed.set(0.0)
        request.operator.mult(probe, observed)
        action_error = _relative(_global_values(observed), augmented_dense @ probe_values)
        captured["augmented_action_error"] = action_error
        assert action_error <= 1.0e-11
        probe.destroy()
        observed.destroy()
        x, relative, operator_dense, solution, global_rhs = _dense_action_solution(
            request.operator,
            request.b,
        )
        expected_operator_error = _relative(operator_dense, augmented_dense)
        captured["dense_operator_error"] = expected_operator_error
        assert expected_operator_error <= 1.0e-11
        captured["physical_fe_rhs_norm"] = float(request.blocks.b_fe.norm())
        captured["aux_solution_norm"] = float(np.linalg.norm(solution[request.n_fe :]))
        reference_relative = float(
            np.linalg.norm(augmented_dense @ solution - global_rhs)
            / max(float(np.linalg.norm(global_rhs)), 1.0e-30)
        )
        captured["reference_relative_residual"] = reference_relative
        captured["augmented_dense"] = augmented_dense
        captured["global_rhs"] = global_rhs
        captured["solution_global"] = solution
        captured["solution_copy"] = x.copy()
        snapshot = Stage4ExternalLinearSolverSnapshot(
            x=x,
            converged_reason=int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL),
            iterations=int(request.operator.getSize()[0]),
            reported_relative_residual=relative,
            condensed_true_residual=relative,
            full_augmented_true_residual=relative,
            ksp_type="test_only_retained_dense_action_oracle",
            pc_type="none",
            residual_limit=1.0e-8,
            no_global_factor=True,
            solver_profile="test_only_retained_p4_core_action",
            assembled_matrix_released_before_solve=False,
            reduced_residual_norm=relative * max(float(request.b.norm()), 1.0e-30),
        )
        return snapshot

    monkeypatch.setattr(
        dtn_port_3d,
        "_retained_effective_recovery_rhs",
        observe_effective_rhs,
    )
    observation: dict[str, object] = {}

    def solution_observer(**kwargs):
        observation.update(kwargs)

    result = run_prepared_3d_case_flow(
        cfg,
        tmp_path / f"retained_dtn_mpi{comm.size}",
        expected_stage_case="stage4_block_grating",
        field_formulation="total_field_dtn_port",
        solve_stage4_dtn_port=True,
        apply_strong_boundary_bc=False,
        linear_solver_port=dtn_port_3d.Stage4NeverMaterializedLinearSolverPort(
            solve_request
        ),
        retained_p4_core_research=True,
        matrix_free_dtn=True,
        solution_observer=solution_observer,
        mesh_data_override=mesh_data,
    )
    dtn_result = observation["dtn_result"]
    solver_info = dtn_result["solver_info"]
    audit = solver_info["cell_static_condensation"]
    system = captured["request"].static_condensed_system
    assert solver_info["retained_p4_core_research"] is True
    assert solver_info["production_qualified"] is False
    assert "research-only retained p4-core" in solver_info["solver_backend"]
    assert audit["research_only"] is True
    assert audit["ordinary_default_changed"] is False
    assert audit["production_qualified"] is False
    assert audit["global_A_materialized"] is False
    assert audit["global_F_materialized"] is False
    assert audit["retained_trace_rows"] == system.numbering.active_trace_rows
    assert audit["retained_core_rows"] == 108 * system.numbering.global_cells
    assert audit["retained_rows"] == system.retained_rows
    assert captured["physical_fe_rhs_norm"] > 1.0e-13
    assert captured["aux_solution_norm"] > 1.0e-13
    incident = np.asarray(dtn_result["goal_context"]["incident_projections"])
    assert np.max(np.abs(incident)) > 1.0e-13
    assert captured["effective_rhs_delta_norm"] > 1.0e-13
    assert captured["effective_rhs_delta_trace_norm"] > 1.0e-13
    assert captured["effective_rhs_delta_interior_relative"] <= 1.0e-11
    assert captured["effective_rhs_delta_core_relative"] <= 1.0e-11
    assert captured["effective_rhs_delta_complement_relative"] <= 1.0e-11
    assert audit["dtn_action_preallocation_audit"]["explicit_c_matrix_count"] == 0
    assert audit["dtn_action_preallocation_audit"]["explicit_d_matrix_count"] == 0
    assert system.audit["global_p6_matrix_or_factor_bytes"] == 0
    assert all(cell.factor.audit["raw_p6_tensor_retained"] is False for cell in system.cells)

    reduced_norm = float(solver_info["reduced_retained_dtn_residual_norm"])
    complement_norm = float(solver_info["eliminated_complement_residual_norm"])
    full_norm = float(solver_info["linear_system_residual_norm"])
    independent_reduced_norm = float(
        np.linalg.norm(
            captured["augmented_dense"] @ captured["solution_global"]
            - captured["global_rhs"]
        )
    )
    assert reduced_norm == pytest.approx(independent_reduced_norm, abs=1.0e-12)
    assert full_norm == pytest.approx(
        np.hypot(independent_reduced_norm, complement_norm),
        abs=1.0e-12,
    )
    assert complement_norm / max(independent_reduced_norm, 1.0) <= 1.0e-11
    assert solver_info["linear_system_relative_residual"] <= 1.0e-11

    effective_rhs = captured["effective_rhs"]
    retained_solution = system.retained_prefix_from_augmented(
        captured["solution_copy"],
        len(dtn_result["goal_context"]["modes"]),
    )
    recovered = system.recover_owned_full_fe_interiors(
        retained_solution,
        effective_rhs,
    )
    effective_values = _global_values(effective_rhs)
    retained_values = _global_values(retained_solution)
    recovery_error = 0.0
    for cell, (rows, values) in zip(system.cells, recovered, strict=True):
        local_rows = np.asarray(
            cell.cell_original_dofs[cell.factor.p6_interior_dofs],
            dtype=np.int64,
        )
        local_rhs = np.zeros(882, dtype=np.complex128)
        local_rhs[cell.factor.p6_interior_dofs] = effective_values[local_rows]
        local_retained = cell.expansion @ retained_values[cell.retained_global_ids]
        expected = cell.factor.recover_p6_coefficients(
            local_retained,
            oriented_rhs=local_rhs,
        )
        recovery_error = max(
            recovery_error,
            _relative(values, expected[cell.factor.p6_interior_dofs]),
            _relative(
                observation["field"].x.petsc_vec.getValues(rows),
                values,
            ),
        )
    recovery_error = float(comm.allreduce(recovery_error, op=MPI.MAX))
    assert recovery_error <= 1.0e-11
    checked_slaves = _assert_mpc_backsubstitution(observation["field"], observation["floquet_data"])
    assert comm.allreduce(checked_slaves, op=MPI.SUM) > 0
    cell_infos = [int(cell.factor.cell_info) for cell in system.cells]
    if not any(cell_infos):
        p6 = build_variable_p_reference_space(HexaEntityDegreeMap.uniform(6))
        control_info = 1 | (2 << 1) | (1 << (3 * 3 + 1)) | (1 << (18 + 1)) | (1 << (18 + 9))
        reference = np.arange(882, dtype=np.complex128)
        oriented = p6.apply_hcurl_dof_transform(reference, cell_info=control_info)
        assert np.linalg.norm(oriented - reference) > 1.0e-13
    retained_solution.destroy()
    effective_rhs.destroy()
    captured["solution_copy"].destroy()
    assert result["external_linear_solver_port"] is True


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="R7b2b1 ordinary retained-flag regression uses serial or MPI2",
)
def test_retained_public_wrapper_default_off(monkeypatch):
    captured = {}

    def implementation(**kwargs):
        captured.update(kwargs)
        return {"wrapper_probe": True}

    monkeypatch.setattr(
        dtn_port_3d,
        "_solve_stage4_dtn_port_total_field_impl",
        implementation,
    )
    result = dtn_port_3d.solve_stage4_dtn_port_total_field(
        a=None,
        L=None,
        V=None,
        mesh_data=None,
        cfg=None,
        floquet_data=None,
        petsc_options={},
        out_dir=Path("."),
        log=lambda *_args, **_kwargs: None,
    )
    assert result["wrapper_probe"] is True
    assert captured["retained_p4_core_research"] is False
    assert captured["matrix_free_dtn"] is False
