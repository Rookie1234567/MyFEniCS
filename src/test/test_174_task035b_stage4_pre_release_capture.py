"""Bounded lifecycle tests for the Stage-4 pre-release capture hook."""

from __future__ import annotations

from dataclasses import replace
from inspect import getsource, signature
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from mpi4py import MPI
from petsc4py import PETSc
import pytest

from src.common.config_3d import SimulationConfig3D
from src.solvers.common_3d_case_flow import (
    _invoke_stage4_pre_release_numerical_capture,
    run_prepared_3d_case_flow,
)
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


def _stage4_config() -> SimulationConfig3D:
    return replace(
        SimulationConfig3D(),
        case_name="task035b_pre_release_capture_fixture",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        unique_output=False,
    )


def _solver_objects() -> tuple[
    PETSc.Mat,
    PETSc.Vec,
    PETSc.Vec,
    PETSc.KSP,
]:
    rows = max(2, MPI.COMM_WORLD.size)
    matrix = PETSc.Mat().createAIJ(
        [rows, rows],
        nnz=1,
        comm=PETSc.COMM_WORLD,
    )
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        matrix.setValue(row, row, PETSc.ScalarType(2.0))
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.set(PETSc.ScalarType(1.0))
    solution = matrix.createVecRight()
    solution.set(PETSc.ScalarType(0.5))
    ksp = PETSc.KSP().create(PETSc.COMM_WORLD)
    ksp.setOperators(matrix)
    return matrix, rhs, solution, ksp


def _invoke(
    callback,
    *,
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    ksp: PETSc.KSP,
    captured_mesh: object | None = None,
):
    function_space = object()
    mesh = object() if captured_mesh is None else captured_mesh
    mesh_data = SimpleNamespace(mesh=mesh)
    config = _stage4_config()
    floquet_data = object()
    goal_context = {"sentinel": object()}
    dtn_result = {
        "A": matrix,
        "b": rhs,
        "x": solution,
        "ksp": ksp,
        "goal_context": goal_context,
    }
    residual_diagnostics = {
        "linear_system_rhs_norm": 1.0,
        "linear_system_solution_norm": 0.5,
        "linear_system_residual_norm": 0.0,
        "linear_system_relative_residual": 0.0,
    }
    solver_diagnostics = {
        "ksp_converged_reason": 4,
        "solver_objects_released": False,
        "postprocess_started": False,
    }
    run_output_identity = {
        "schema_version": (
            "task035b.stage4-pre-release-run-output-identity.v1"
        ),
        "case_name": config.case_name,
        "output_directory": "/tmp/task035b-pre-release-fixture",
        "identity_constructed_by_case_flow": True,
    }
    audit = _invoke_stage4_pre_release_numerical_capture(
        callback,
        communicator=MPI.COMM_WORLD,
        function_space=function_space,
        mesh_data=mesh_data,  # type: ignore[arg-type]
        config=config,
        floquet_data=floquet_data,  # type: ignore[arg-type]
        system_A=matrix,
        system_b=rhs,
        system_x=solution,
        system_ksp=ksp,
        dtn_result=dtn_result,
        residual_diagnostics=residual_diagnostics,
        solver_diagnostics=solver_diagnostics,
        run_output_identity=run_output_identity,
        solver_release_scheduled_after_capture=True,
    )
    return SimpleNamespace(
        audit=audit,
        function_space=function_space,
        mesh=mesh,
        mesh_data=mesh_data,
        config=config,
        floquet_data=floquet_data,
        goal_context=goal_context,
        dtn_result=dtn_result,
        residual_diagnostics=residual_diagnostics,
        solver_diagnostics=solver_diagnostics,
        run_output_identity=run_output_identity,
    )


def test_hook_is_default_off_and_stage4_forwarding_is_explicit(
    tmp_path: Path,
) -> None:
    for function in (
        run_prepared_3d_case_flow,
        run_stage4b_block_grating_3d_case,
    ):
        parameter = signature(function).parameters[
            "stage4_pre_release_numerical_capture"
        ]
        assert parameter.default is None
    assert not hasattr(
        SimulationConfig3D(),
        "stage4_pre_release_numerical_capture",
    )

    def callback(**_state) -> None:
        return None
    with patch(
        "src.solvers.solve_maxwell_3d_stage_4b_block_grating."
        "run_prepared_3d_case_flow",
        return_value={"sentinel": True},
    ) as prepared:
        result = run_stage4b_block_grating_3d_case(
            _stage4_config(),
            tmp_path,
            stage4_pre_release_numerical_capture=callback,
        )
    assert result == {"sentinel": True}
    assert (
        prepared.call_args.kwargs[
            "stage4_pre_release_numerical_capture"
        ]
        is callback
    )

    ordinary = SimulationConfig3D()
    with pytest.raises(
        ValueError,
        match="requires the Stage-4 DtN flow",
    ):
        run_prepared_3d_case_flow(
            ordinary,
            tmp_path,
            expected_stage_case=ordinary.stage_case,
            field_formulation="total_field",
            stage4_pre_release_numerical_capture=callback,
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in {1, 2},
    reason="focused serial/MPI2 pre-release identity",
)
def test_live_borrowed_identity_and_read_only_views() -> None:
    matrix, rhs, solution, ksp = _solver_objects()
    captured: dict[str, object] = {}

    def callback(**state) -> None:
        captured.update(state)
        assert int(state["A"].handle) != 0
        assert int(state["b"].handle) != 0
        assert int(state["x"].handle) != 0
        assert int(state["ksp"].handle) != 0
        assert isinstance(state["dtn_result"], MappingProxyType)
        assert isinstance(state["goal_context"], MappingProxyType)
        assert isinstance(
            state["residual_diagnostics"],
            MappingProxyType,
        )
        assert isinstance(
            state["run_output_identity"],
            MappingProxyType,
        )
        assert (
            state["borrowed_object_contract"]["semantics"]
            == "borrowed_until_callback_returns"
        )
        assert (
            state["borrowed_object_contract"][
                "solver_objects_released_at_entry"
            ]
            is False
        )
        assert (
            state["borrowed_object_contract"][
                "postprocess_started_at_entry"
            ]
            is False
        )

    try:
        fixture = _invoke(
            callback,
            matrix=matrix,
            rhs=rhs,
            solution=solution,
            ksp=ksp,
        )
        assert captured["function_space"] is fixture.function_space
        assert captured["mesh"] is fixture.mesh
        assert captured["mesh_data"] is fixture.mesh_data
        assert captured["config"] is fixture.config
        assert captured["floquet_data"] is fixture.floquet_data
        assert captured["A"] is matrix
        assert captured["b"] is rhs
        assert captured["x"] is solution
        assert captured["ksp"] is ksp
        assert captured["dtn_result"]["A"] is matrix
        assert (
            captured["goal_context"]["sentinel"]
            is fixture.goal_context["sentinel"]
        )
        assert dict(captured["residual_diagnostics"]) == (
            fixture.residual_diagnostics
        )
        assert dict(captured["solver_diagnostics"]) == (
            fixture.solver_diagnostics
        )
        assert dict(captured["run_output_identity"]) == (
            fixture.run_output_identity
        )
        assert int(matrix.handle) != 0
        assert int(rhs.handle) != 0
        assert int(solution.handle) != 0
        assert int(ksp.handle) != 0
        audit = fixture.audit
        assert audit["requested"] is True
        assert audit["invoked"] is True
        assert audit["completed_collectively"] is True
        assert audit["solver_objects_live_at_entry"] is True
        assert audit["solver_objects_live_after_return"] is True
        assert audit["petsc_object_identity_unchanged"] is True
        assert audit["callback_returned_none_on_all_ranks"] is True
        assert audit["invoked_before_solver_release"] is True
        assert audit["invoked_before_postprocess"] is True
        assert audit["solver_release_scheduled_after_capture"] is True
        assert audit["ordinary_default_changed"] is False
        assert "formal_actual_pde_ready" not in audit
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_case_flow_places_capture_before_destroy_and_postprocess() -> None:
    source = getsource(run_prepared_3d_case_flow)
    capture_position = source.index(
        "_invoke_stage4_pre_release_numerical_capture("
    )
    destroy_position = source.index("system_ksp.destroy()")
    postprocess_position = source.index("save_airbox_3d_fields(")
    assert capture_position < destroy_position < postprocess_position
    assert '"source_commit_sha"' not in source
    assert '"configured_condensed_cache_source_sha"' in source
    assert '"formal_source_identity_provided": False' in source


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in {1, 2},
    reason="focused serial/MPI2 collective failure",
)
def test_callback_exception_is_propagated_collectively() -> None:
    matrix, rhs, solution, ksp = _solver_objects()

    def callback(**_state) -> None:
        if MPI.COMM_WORLD.rank == 0:
            raise ValueError("rank-zero-capture-failure")

    try:
        with pytest.raises(
            RuntimeError,
            match=(
                "Stage-4 pre-release numerical capture failed "
                "collectively"
            ),
        ) as error:
            _invoke(
                callback,
                matrix=matrix,
                rhs=rhs,
                solution=solution,
                ksp=ksp,
            )
        message = str(error.value)
        messages = MPI.COMM_WORLD.allgather(message)
        assert len(set(messages)) == 1
        assert '"exception_type":"ValueError"' in message
        assert '"rank":0' in message
        assert "rank-zero-capture-failure" in message
        assert int(matrix.handle) != 0
        assert int(rhs.handle) != 0
        assert int(solution.handle) != 0
        assert int(ksp.handle) != 0
    finally:
        ksp.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()
