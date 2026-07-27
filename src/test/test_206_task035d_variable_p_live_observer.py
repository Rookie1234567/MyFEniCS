from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.common.config_3d import (
    ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.solvers import dtn_port_3d
from src.solvers.hcurl_variable_p_reduction import (
    VariablePRecoveredSolution,
)
from src.solvers.dtn_port_3d import (
    Stage4VariablePLiveObserverError,
    _deep_readonly_copy,
    _invoke_collective_variable_p_live_observer,
    _readonly_goal_context,
)
from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
    run_stage4b_block_grating_3d_case,
)


def _vector() -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(3, comm=MPI.COMM_WORLD)
    vector.set(PETSc.ScalarType(0.0))
    vector.assemble()
    return vector


def _borrowed_view(recovered: VariablePRecoveredSolution):
    matrix = PETSc.Mat().createAIJ(
        size=(3, 3),
        nnz=1,
        comm=MPI.COMM_WORLD,
    )
    start, stop = matrix.getOwnershipRange()
    for row in range(start, stop):
        matrix.setValue(row, row, PETSc.ScalarType(2.0))
    matrix.assemble()
    rhs = _vector()
    solution = _vector()
    field_vector = _vector()
    solver = PETSc.KSP().create(MPI.COMM_WORLD)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.NONE)
    solver.setOperators(matrix)
    view = SimpleNamespace(
        A=matrix,
        b=rhs,
        x=solution,
        field=SimpleNamespace(
            x=SimpleNamespace(petsc_vec=field_vector)
        ),
        ksp=solver,
        recovered=recovered,
    )
    return view, (solver, field_vector, solution, rhs, matrix)


def test_recovered_solution_owns_idempotent_vector_lifecycle() -> None:
    recovered = VariablePRecoveredSolution(
        field=object(),
        active_full_solution=_vector(),
        active_full_rhs=_vector(),
        active_auxiliary_interior_action=_vector(),
        audit={"pass": True},
    )
    with recovered as borrowed:
        assert borrowed._destroyed is False
        assert borrowed.active_full_solution.getSize() == 3
        assert borrowed.active_full_rhs.getSize() == 3
        assert borrowed.active_auxiliary_interior_action is not None
        assert borrowed.active_auxiliary_interior_action.getSize() == 3
    assert recovered._destroyed is True
    assert recovered.active_full_solution is None
    assert recovered.active_full_rhs is None
    assert recovered.active_auxiliary_interior_action is None
    recovered.destroy()
    assert recovered._destroyed is True


def test_live_evidence_snapshots_are_deep_readonly() -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    auxiliary = np.arange(len(modes), dtype=np.complex128)
    context = _readonly_goal_context(
        {
            "modes": modes,
            "auxiliary_values": auxiliary,
            "incident_projections": np.zeros_like(auxiliary),
            "normalization": "fixture",
        }
    )
    with pytest.raises(ValueError):
        context["auxiliary_values"][0] = 1.0
    with pytest.raises(ValueError):
        context["modes"][0].e_vector[0] = 1.0
    nested = _deep_readonly_copy(
        {"orders": [{"value": [1.0, 2.0]}]}
    )
    with pytest.raises(TypeError):
        nested["orders"][0]["value"] = (3.0,)
    assert auxiliary[0] == 0.0
    assert modes[0].e_vector.flags.writeable is True


def test_recovered_solution_cleanup_is_best_effort_and_idempotent() -> None:
    calls: list[str] = []

    class DestroyProbe:
        def __init__(self, name: str, *, fail: bool = False):
            self.name = name
            self.fail = fail

        def destroy(self) -> None:
            calls.append(self.name)
            if self.fail:
                raise RuntimeError(f"{self.name} sentinel")

    recovered = VariablePRecoveredSolution(
        field=object(),
        active_full_solution=DestroyProbe("solution"),
        active_full_rhs=DestroyProbe("rhs", fail=True),
        active_auxiliary_interior_action=DestroyProbe("auxiliary"),
        audit={"pass": True},
    )
    with pytest.raises(RuntimeError, match="rhs sentinel"):
        recovered.destroy()
    assert calls == ["solution", "rhs", "auxiliary"]
    assert recovered._destroyed is True
    assert recovered.active_full_solution is None
    assert recovered.active_full_rhs is None
    assert recovered.active_auxiliary_interior_action is None
    recovered.destroy()
    assert calls == ["solution", "rhs", "auxiliary"]


def test_collective_callback_failure_closes_vectors_on_every_rank() -> None:
    recovered = VariablePRecoveredSolution(
        field=object(),
        active_full_solution=_vector(),
        active_full_rhs=_vector(),
        active_auxiliary_interior_action=None,
        audit={"pass": True},
    )
    view, petsc_objects = _borrowed_view(recovered)

    def fail_on_rank_zero(_view) -> None:
        if MPI.COMM_WORLD.rank == 0:
            raise RuntimeError("rank-zero observer sentinel")

    try:
        with pytest.raises(
            Stage4VariablePLiveObserverError,
            match="rank-zero observer sentinel",
        ):
            _invoke_collective_variable_p_live_observer(
                fail_on_rank_zero,
                view,
                MPI.COMM_WORLD,
            )
        assert recovered._destroyed is True
    finally:
        for petsc_object in petsc_objects:
            petsc_object.destroy()


def test_collective_callback_rejects_borrowed_solution_mutation() -> None:
    recovered = VariablePRecoveredSolution(
        field=object(),
        active_full_solution=_vector(),
        active_full_rhs=_vector(),
        active_auxiliary_interior_action=None,
        audit={"pass": True},
    )
    view, petsc_objects = _borrowed_view(recovered)

    def mutate_solution(borrowed_view) -> None:
        borrowed_view.x.set(PETSc.ScalarType(1.0))

    try:
        with pytest.raises(
            Stage4VariablePLiveObserverError,
            match="BorrowedObjectMutation",
        ):
            _invoke_collective_variable_p_live_observer(
                mutate_solution,
                view,
                MPI.COMM_WORLD,
            )
        assert recovered._destroyed is True
    finally:
        for petsc_object in petsc_objects:
            petsc_object.destroy()


@pytest.mark.parametrize("implementation_raises", (False, True))
def test_dtn_wrapper_closes_recovery_on_every_exit(
    monkeypatch,
    tmp_path,
    implementation_raises: bool,
) -> None:
    captured: dict[str, VariablePRecoveredSolution] = {}

    def fake_impl(**kwargs):
        recovered = VariablePRecoveredSolution(
            field=object(),
            active_full_solution=_vector(),
            active_full_rhs=_vector(),
            active_auxiliary_interior_action=None,
            audit={"pass": True},
        )
        kwargs["_recovery_cleanup_sink"].append(recovered)
        captured["recovered"] = recovered
        if implementation_raises:
            raise RuntimeError("tail failure sentinel")
        return {"status": "fixture"}

    monkeypatch.setattr(
        dtn_port_3d,
        "_solve_stage4_dtn_port_total_field_impl",
        fake_impl,
    )
    kwargs = {
        "a": None,
        "L": None,
        "V": None,
        "mesh_data": None,
        "cfg": None,
        "floquet_data": None,
        "petsc_options": {},
        "out_dir": tmp_path,
        "log": lambda _message: None,
    }
    if implementation_raises:
        with pytest.raises(RuntimeError, match="tail failure sentinel"):
            dtn_port_3d.solve_stage4_dtn_port_total_field(**kwargs)
    else:
        assert dtn_port_3d.solve_stage4_dtn_port_total_field(
            **kwargs
        ) == {"status": "fixture"}
    recovered = captured["recovered"]
    assert recovered._destroyed is True
    assert recovered.active_full_solution is None
    assert recovered.active_full_rhs is None


def test_live_observer_rejects_non_variable_backend_before_mesh(
    tmp_path,
) -> None:
    config = target_stage4_config(degree=2, h_nm=50.0)
    with pytest.raises(
        ValueError,
        match="requires the exact-sequence assembly-time variable-p backend",
    ):
        run_stage4b_block_grating_3d_case(
            config,
            tmp_path / "must_not_build",
            variable_p_live_observer=lambda _view: None,
        )
    assert not (tmp_path / "must_not_build").exists()


def test_rank_inconsistent_live_observer_fails_before_validation(
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-inconsistent callback gate requires MPI2")
    config = target_stage4_config(degree=2, h_nm=50.0)
    observer = (
        (lambda _view: None) if MPI.COMM_WORLD.rank == 0 else None
    )
    with pytest.raises(ValueError, match="enabled on every MPI rank"):
        run_stage4b_block_grating_3d_case(
            config,
            tmp_path / "must_not_build",
            variable_p_live_observer=observer,
        )
    assert not (tmp_path / "must_not_build").exists()


def test_live_and_late_observers_fail_closed_before_mesh(tmp_path) -> None:
    config = replace(
        target_stage4_config(degree=2, h_nm=50.0),
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
    )
    with pytest.raises(ValueError, match="cannot be enabled together"):
        run_stage4b_block_grating_3d_case(
            config,
            tmp_path / "must_not_build",
            solution_observer=lambda **_kwargs: None,
            variable_p_live_observer=lambda _view: None,
        )
    assert not (tmp_path / "must_not_build").exists()


@pytest.mark.parametrize(
    "diagnostic_field",
    (
        "matrix_diagnostics_assemble_only",
        "matrix_diagnostics_factorization_only",
    ),
)
def test_live_observer_rejects_diagnostic_only_modes_before_mesh(
    tmp_path,
    diagnostic_field: str,
) -> None:
    config = replace(
        target_stage4_config(degree=2, h_nm=50.0),
        stage4_full3d_assembly_backend=(
            ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND
        ),
        **{diagnostic_field: True},
    )
    with pytest.raises(ValueError, match="requires a complete solve"):
        run_stage4b_block_grating_3d_case(
            config,
            tmp_path / "must_not_build",
            variable_p_live_observer=lambda _view: None,
        )
    assert not (tmp_path / "must_not_build").exists()
