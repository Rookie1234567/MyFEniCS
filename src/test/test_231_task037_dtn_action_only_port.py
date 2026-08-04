from dataclasses import replace
import json

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.condensed_dtn as condensed_dtn
import src.solvers.dtn_port_3d as dtn_port_3d
import src.solvers.hcurl_assembly_time_condensation as assembly_time
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
    extract_canonical_full_fe_packets,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


def _read_orders(path):
    payload = None
    if MPI.COMM_WORLD.rank == 0:
        payload = json.loads((path / "dtn_port_diffraction_orders_3d.json").read_text())
    payload = MPI.COMM_WORLD.bcast(payload, root=0)
    return {
        (
            row["side"],
            int(row["m"]),
            int(row["n"]),
            row["polarization"],
        ): row
        for row in payload["orders"]
    }


def _collect_packets(packets, comm):
    gathered = comm.gather(tuple(packets), root=0)
    merged = (
        tuple(packet for rank_packets in gathered for packet in rank_packets)
        if comm.rank == 0
        else None
    )
    return tuple(comm.bcast(merged, root=0))


def _active_packets_from_augmented(request, x, comm):
    active = request.static_condensed_system.create_active_vector()
    active_start, active_end = map(int, active.getOwnershipRange())
    x_start, x_end = map(int, x.getOwnershipRange())
    assert x_start == active_start
    local_active = active_end - active_start
    x_values = np.asarray(x.getArray(readonly=True), dtype=np.complex128)
    assert x_end - x_start >= local_active
    active.getArray()[:] = x_values[:local_active]
    active.assemble()
    packets, audit = extract_canonical_active_trace_packets(
        request.static_condensed_system,
        request.function_space,
        request.floquet_data,
        active,
    )
    active.destroy()
    return _collect_packets(packets, comm), audit


def _observe_solution(observation, **kwargs):
    field = kwargs["field"]
    packets, _audit = extract_canonical_full_fe_packets(
        field.function_space,
        field.x.petsc_vec,
        kwargs["floquet_data"],
    )
    packets = _collect_packets(packets, field.function_space.mesh.comm)
    if "assembled_full_packets" not in observation:
        observation["assembled_full_packets"] = packets
        comparison = compare_canonical_packets(
            packets, packets, relative_tolerance=1.0e-8
        )
        assert comparison["pass"]
        assert comparison["relative_coefficient_l2"] <= 1.0e-8
        return
    comparison = compare_canonical_packets(
        packets,
        observation["assembled_full_packets"],
        relative_tolerance=1.0e-8,
    )
    observation["full_packet_comparison"] = comparison
    assert comparison["pass"]
    assert comparison["relative_coefficient_l2"] <= 1.0e-8


def _dense_action_solution(operator, rhs):
    comm = operator.getComm().tompi4py()
    size = int(operator.getSize()[0])
    local_start, local_end = rhs.getOwnershipRange()
    local_dense = np.empty((local_end - local_start, size), dtype=np.complex128)
    source = rhs.duplicate()
    target = rhs.duplicate()
    for column in range(size):
        source.set(0.0)
        if local_start <= column < local_end:
            source.setValue(column, 1.0)
        source.assemble()
        operator.mult(source, target)
        local_dense[:, column] = target.getArray(readonly=True)
    dense = np.vstack(comm.allgather(local_dense))
    assert dense.shape == (size, size)
    global_rhs = np.concatenate(comm.allgather(rhs.getArray(readonly=True)))
    solution = np.linalg.solve(dense, global_rhs)
    result = rhs.duplicate()
    result.getArray()[:] = solution[local_start:local_end]
    result.assemble()
    residual = rhs.duplicate()
    operator.mult(result, residual)
    residual.axpy(PETSc.ScalarType(-1.0), rhs)
    residual_norm = float(residual.norm())
    relative = residual_norm / max(float(rhs.norm()), 1.0e-30)
    source.destroy()
    target.destroy()
    residual.destroy()
    return result, relative, size, dense, global_rhs, solution


def _solve_action_only(request, observation=None):
    assert request.static_condensed_system.matrix is None
    assert request.blocks.F is None
    assert request.fine_operator.getSize() == (request.n_fe, request.n_fe)
    x, relative, size, dense, global_rhs, solution = _dense_action_solution(
        request.operator, request.b
    )
    active_packets, active_audit = _active_packets_from_augmented(
        request, x, request.operator.getComm().tompi4py()
    )
    residual_norm = relative * max(float(request.b.norm()), 1.0e-30)
    if observation is not None:
        reference = observation["assembled"]
        active_comparison = compare_canonical_packets(
            active_packets,
            reference["active_packets"],
            relative_tolerance=1.0e-8,
        )
        action_errors = []
        vectors = (
            np.ones(request.n_fe + request.n_aux, dtype=np.complex128),
            np.arange(request.n_fe + request.n_aux, dtype=np.float64) + 0.25j,
            np.linspace(0.5, 1.5, request.n_fe + request.n_aux) - 0.5j,
            np.random.default_rng(231).standard_normal(request.n_fe + request.n_aux)
            + 1j
            * np.random.default_rng(231).standard_normal(request.n_fe + request.n_aux),
        )
        for vector in vectors:
            expected = reference["matrix"] @ vector
            observed = dense @ vector
            action_errors.append(
                float(
                    np.linalg.norm(observed - expected)
                    / max(np.linalg.norm(expected), 1.0e-30)
                )
            )
        observation["action"] = {
            "active_packet_audit": active_audit,
            "active_packet_comparison": active_comparison,
            "matrix_max_abs_error": float(np.max(np.abs(dense - reference["matrix"]))),
            "rhs_max_abs_error": float(np.max(np.abs(global_rhs - reference["rhs"]))),
            "max_vector_action_relative_error": max(action_errors),
            "solution_relative_error": float(
                np.linalg.norm(solution - reference["solution"])
                / max(np.linalg.norm(reference["solution"]), 1.0e-30)
            ),
        }
        assert active_comparison["pass"]
        assert active_comparison["relative_coefficient_l2"] <= 1.0e-8
        assert observation["action"]["matrix_max_abs_error"] <= 1.0e-11
        assert observation["action"]["rhs_max_abs_error"] <= 1.0e-12
        assert observation["action"]["max_vector_action_relative_error"] <= 1.0e-11
        assert observation["action"]["solution_relative_error"] <= 1.0e-8
    reason = int(
        PETSc.KSP.ConvergedReason.CONVERGED_RTOL
        if relative <= 1.0e-8
        else PETSc.KSP.ConvergedReason.DIVERGED_ITS
    )
    return dtn_port_3d.Stage4ExternalLinearSolverSnapshot(
        x=x,
        converged_reason=reason,
        iterations=size,
        reported_relative_residual=relative,
        condensed_true_residual=relative,
        full_augmented_true_residual=relative,
        ksp_type="test_only_dense_oracle_not_resource_evidence",
        pc_type="none",
        residual_limit=1.0e-8,
        no_global_factor=True,
        solver_profile="task037_m1c_never_materialized_dtn",
        assembled_matrix_released_before_solve=False,
        reduced_residual_norm=residual_norm,
    )


def _solve_assembled(request, observation=None):
    x, relative, size, dense, global_rhs, solution = _dense_action_solution(
        request.A, request.b
    )
    active_packets, active_audit = _active_packets_from_augmented(
        request, x, request.A.getComm().tompi4py()
    )
    residual_norm = relative * max(float(request.b.norm()), 1.0e-30)
    if observation is not None:
        observation["assembled"] = {
            "active_packet_audit": active_audit,
            "active_packets": active_packets,
            "matrix": dense,
            "rhs": global_rhs,
            "solution": solution,
        }
    reason = int(
        PETSc.KSP.ConvergedReason.CONVERGED_RTOL
        if relative <= 1.0e-8
        else PETSc.KSP.ConvergedReason.DIVERGED_ITS
    )
    return dtn_port_3d.Stage4ExternalLinearSolverSnapshot(
        x=x,
        converged_reason=reason,
        iterations=size,
        reported_relative_residual=relative,
        condensed_true_residual=relative,
        full_augmented_true_residual=relative,
        ksp_type="test_only_dense_oracle_not_resource_evidence",
        pc_type="none",
        residual_limit=1.0e-8,
        no_global_factor=True,
        solver_profile="assembled",
        assembled_matrix_released_before_solve=False,
        reduced_residual_norm=residual_norm,
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="M1c tiny action-only port supports serial/MPI2",
)
def test_tiny_dtn_port_uses_never_materialized_action_path(monkeypatch, tmp_path):
    def fail_preallocation(*_args, **_kwargs):
        raise AssertionError("action-only port called global trace preallocation")

    def fail_extract(*_args, **_kwargs):
        raise AssertionError("action-only port extracted an augmented matrix")

    cfg = replace(
        target_stage4_config(degree=2, h_nm=100.0),
        case_name=f"task037_m1c_tiny_mpi{MPI.COMM_WORLD.size}",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        direct_release_solver_before_postprocess=True,
        unique_output=False,
    )
    observation = {}

    def solution_observer(**kwargs):
        _observe_solution(observation, **kwargs)

    assembled = run_stage4b_block_grating_3d_case(
        cfg,
        tmp_path / "assembled_tiny",
        solution_observer=solution_observer,
        linear_solver_port=lambda request: _solve_assembled(request, observation),
    )
    assert assembled["case_status"] == "completed"
    assert assembled["official_result"] is True
    assert assembled["external_rta_gate_pass"] is True
    with monkeypatch.context() as context:
        context.setattr(
            assembly_time,
            "_distributed_trace_preallocation",
            fail_preallocation,
        )
        context.setattr(
            condensed_dtn,
            "extract_petsc_condensed_blocks",
            fail_extract,
        )
        context.setattr(
            dtn_port_3d,
            "_copy_base_matrix_to_augmented",
            fail_extract,
        )
        result = run_stage4b_block_grating_3d_case(
            cfg,
            tmp_path / "m1c_tiny",
            solution_observer=solution_observer,
            linear_solver_port=dtn_port_3d.Stage4NeverMaterializedLinearSolverPort(
                lambda request: _solve_action_only(request, observation)
            ),
        )
    assert result["case_status"] == "completed"
    assert result["official_result"] is True
    assert result["postprocess_skipped"] is False
    assert result["external_linear_solver_port"] is True
    assert result["external_rta_gate_pass"] is True
    assert result["stage4_assembly_time_cell_static_condensation"] is True
    assert result["matrix_stats"]["global_A_materialized"] is False
    assert (
        result["stage4_dtn_augmented_matrix_stats_after_finalize"][
            "global_F_materialized"
        ]
        is False
    )
    audit = result["cell_static_condensation"]
    assert audit["matrix_materialized"] is False
    assert audit["action_only_setup"] is True
    assert audit["dtn_action_preallocation_audit"]["python_triplet_cache"] is False
    assert assembled["matrix_stats"]["matrix_type"] != "python_action_only"
    for key in ("linear_system_relative_residual", "R_total", "T_total"):
        assert result[key] == pytest.approx(assembled[key], abs=1.0e-8)
    assert result["A_balance"] == pytest.approx(assembled["A_balance"], abs=1.0e-8)
    assert observation["action"]["matrix_max_abs_error"] <= 1.0e-11
    assert observation["action"]["rhs_max_abs_error"] <= 1.0e-12
    assert observation["action"]["max_vector_action_relative_error"] <= 1.0e-11
    assert observation["action"]["solution_relative_error"] <= 1.0e-8
    assert observation["full_packet_comparison"]["pass"]
    assert observation["full_packet_comparison"]["relative_coefficient_l2"] <= 1.0e-8
    assembled_orders = _read_orders(tmp_path / "assembled_tiny")
    action_orders = _read_orders(tmp_path / "m1c_tiny")
    assert set(assembled_orders) == set(action_orders)
    for key in assembled_orders:
        left = assembled_orders[key]
        right = action_orders[key]
        assert right["power_ratio"] == pytest.approx(left["power_ratio"], abs=1.0e-8)
        left_boundary = complex(*left["outgoing_amplitude_at_boundary"])
        right_boundary = complex(*right["outgoing_amplitude_at_boundary"])
        assert abs(right_boundary - left_boundary) <= 1.0e-8
    for key in (
        "A_volume_total",
        "A_volume_grating",
        "A_volume_substrate",
        "energy_closure_error_port_volume",
    ):
        left = assembled.get(key)
        right = result.get(key)
        if left is None or right is None:
            assert left is None and right is None
        else:
            assert right == pytest.approx(left, abs=1.0e-8)
