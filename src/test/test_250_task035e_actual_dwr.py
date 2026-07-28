from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.blind_controller.contracts import FORMAL_GOAL_IDS
from src.adaptivity.task035e_actual_dwr import (
    ACTUAL_DWR_SCHEMA,
    Task035eActualDWRError,
    evaluate_task035e_actual_dwr,
)


SOURCE_SHA = "1" * 40
FOREST_SHA = "2" * 64
DEGREE_SHA = "3" * 64


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_plan(path: Path, *, source_sha: str = SOURCE_SHA) -> str:
    payload = {
        "schema_version": (
            "task035e.stage4-multilevel-local-h-refinement-plan.v1"
        ),
        "status": "stage4_balanced_multilevel_local_h_plan",
        "variable_trace_from_cell_degrees": True,
        "expected_forest": {"leaf_catalog_sha256": FOREST_SHA},
        "cell_interior_degree_plan_sha256": DEGREE_SHA,
        "provenance": {
            "schema_version": "task035e.blind-solver-plan-transition.v2",
            "status": "blind_solver_plan_transition_closed",
            "source_sha": source_sha,
            "cycle_index": 1,
        },
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return _file_sha256(path)


def _dense_matrix(size: int) -> np.ndarray:
    matrix = np.zeros((size, size), dtype=np.complex128)
    for row in range(size):
        matrix[row, row] = 3.4 + 0.03 * row + 0.08j
        if row > 0:
            matrix[row, row - 1] = -0.23 + 0.015j * (row + 1)
        if row + 1 < size:
            matrix[row, row + 1] = 0.14 - 0.021j * (row + 1)
    matrix[0, -1] = 0.025 + 0.014j
    matrix[-1, 0] = -0.019 + 0.006j
    return matrix


def _matrix(
    dense: np.ndarray,
    comm: MPI.Intracomm,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=dense.shape,
        nnz=4,
        comm=comm,
    )
    matrix.setUp()
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = np.flatnonzero(dense[row] != 0.0)
        matrix.setValues(
            [row],
            columns.astype(PETSc.IntType, copy=False),
            np.asarray(
                dense[row, columns], dtype=PETSc.ScalarType
            ).reshape(1, -1),
        )
    matrix.assemble()
    return matrix


def _vector_from_global(
    values: np.ndarray,
    comm: MPI.Intracomm,
) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(len(values), comm=comm)
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(
        values[start:end], dtype=PETSc.ScalarType
    )
    vector.assemble()
    return vector


def _port_audit() -> dict[str, object]:
    return {
        "schema_version": (
            "task035d.variable-p-trace-only-port-operator.v1"
        ),
        "pass": True,
        "checks": {
            "trace_functionals_present": True,
            "trace_only_gate": True,
            "removed_interior_is_qualified_roundoff": True,
            "no_auxiliary_interior_columns": True,
            "external_operator_content_hash": True,
            "external_rhs_content_hash": True,
            "zero_volume_base_rhs": True,
        },
        "auxiliary_interior_columns_allocated": False,
        "external_operator_content_sha256": "4" * 64,
        "external_rhs_content_sha256": "5" * 64,
    }


class _Fixture:
    def __init__(
        self,
        plan_path: Path,
        plan_sha: str,
        *,
        comm: MPI.Intracomm,
    ) -> None:
        self.comm = comm
        self.size = max(5, 2 * comm.size + 1)
        self.dense = _dense_matrix(self.size)
        self.matrix = _matrix(self.dense, comm)
        rows = np.arange(self.size, dtype=np.float64)
        self.shadow_exact_values = (
            0.2 * np.cos(0.17 * (rows + 1.0))
            + 0.11j * np.sin(0.13 * (rows + 1.0))
        ).astype(np.complex128)
        self.current_values = (
            self.shadow_exact_values
            + 0.018 * np.sin(0.31 * (rows + 1.0))
            - 0.009j * np.cos(0.23 * (rows + 1.0))
        ).astype(np.complex128)
        rhs_values = self.dense @ self.shadow_exact_values
        self.rhs = _vector_from_global(rhs_values, comm)
        self.shadow_solution = self.rhs.duplicate()
        self.ksp = PETSc.KSP().create(comm)
        self.ksp.setType(PETSc.KSP.Type.PREONLY)
        self.ksp.getPC().setType(PETSc.PC.Type.LU)
        self.ksp.getPC().setFactorSolverType("mumps")
        self.ksp.setOperators(self.matrix)
        self.ksp.setErrorIfNotConverged(True)
        self.ksp.solve(self.rhs, self.shadow_solution)
        assert self.ksp.getConvergedReason() > 0
        self.current = _vector_from_global(self.current_values, comm)
        self.gradients: dict[str, PETSc.Vec] = {}
        self.gradient_values: dict[str, np.ndarray] = {}
        for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS):
            phase = 0.07 * (goal_index + 1)
            values = (
                0.3
                * np.cos(phase + 0.11 * (rows + 1.0))
                + 0.17j
                * np.sin(0.5 * phase + 0.09 * (rows + 1.0))
            ).astype(np.complex128)
            values[goal_index % self.size] += 0.4 + 0.03j
            self.gradient_values[goal_id] = values
            self.gradients[goal_id] = _vector_from_global(values, comm)
        context = SimpleNamespace(
            plan_path=str(plan_path),
            plan_file_sha256=plan_sha,
            forest=SimpleNamespace(
                audit={
                    "schema_version": "task035d.dyadic-hexa-forest.v1",
                    "pass": True,
                    "leaf_catalog_sha256": FOREST_SHA,
                }
            ),
        )
        system = SimpleNamespace(
            entity_map=SimpleNamespace(
                active_rows=self.size + 2,
                active_trace_rows=self.size,
            ),
            active_trace_rows=self.size - 1,
            appended_rows=1,
        )
        reduction = SimpleNamespace(
            system=system,
            degree_plan=SimpleNamespace(
                audit={
                    "schema_version": (
                        "task035e.local-h-variable-exact-sequence-plan.v1"
                    ),
                    "status": (
                        "local_h_variable_exact_sequence_plan_closed"
                    ),
                    "pass": True,
                    "cell_degree_plan_sha256": DEGREE_SHA,
                }
            ),
            build_audit={
                "schema_version": (
                    "task035d.variable-p-assembly-reduction.v1"
                ),
                "inactive_p6_rows_globally_numbered": False,
            },
        )
        self.view = SimpleNamespace(
            mesh_data=SimpleNamespace(
                mesh=SimpleNamespace(comm=comm),
                local_h_context=context,
            ),
            A=self.matrix,
            b=self.rhs,
            x=self.shadow_solution,
            ksp=self.ksp,
            reduction=reduction,
            floquet_data=SimpleNamespace(
                phase_x=np.exp(0.2j),
                phase_y=np.exp(-0.3j),
                phase_corner=np.exp(-0.1j),
                constraint_mode_resolved="topological_trace_p6",
                num_constraints=24,
                num_x_constraints=8,
                num_y_constraints=8,
                num_corner_constraints=8,
                used_full_boundary_gather=False,
                created_dense_boundary_square=False,
            ),
            full_active_residual={
                "linear_system_relative_residual": 3.0e-14,
                "full_explicit_true_residual_pass": True,
            },
            primal_solver_telemetry={
                "converged_reason": int(
                    self.ksp.getConvergedReason()
                ),
                "iterations": int(self.ksp.getIterationNumber()),
                "ksp_type": "preonly",
                "pc_type": "lu",
                "pc_factor_solver_type": "mumps",
            },
            port_operator_audit=_port_audit(),
        )

    def destroy(self) -> None:
        for gradient in self.gradients.values():
            gradient.destroy()
        self.current.destroy()
        self.ksp.destroy()
        self.shadow_solution.destroy()
        self.rhs.destroy()
        self.matrix.destroy()


def _evaluate(fixture: _Fixture, plan_sha: str):
    return evaluate_task035e_actual_dwr(
        fixture.view,
        fixture.current,
        fixture.gradients,
        source_sha=SOURCE_SHA,
        expected_shadow_plan_sha256=plan_sha,
        shadow_kind="p-shadow",
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial actual-DWR component test",
)
def test_serial_actual_dwr_matches_dense_59_goal_algebra(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "shadow-plan.json"
    plan_sha = _write_plan(plan_path)
    fixture = _Fixture(plan_path, plan_sha, comm=MPI.COMM_WORLD)
    protected = {
        "matrix": int(fixture.matrix.stateGet()),
        "rhs": int(fixture.rhs.stateGet()),
        "shadow": int(fixture.shadow_solution.stateGet()),
        "current": int(fixture.current.stateGet()),
        **{
            goal_id: int(vector.stateGet())
            for goal_id, vector in fixture.gradients.items()
        },
    }
    try:
        result = _evaluate(fixture, plan_sha)
        report = result.report
        assert report["schema_version"] == ACTUAL_DWR_SCHEMA
        assert report["status"] == "actual_live_shadow_dwr_pass"
        assert len(report["goals"]) == len(FORMAL_GOAL_IDS) == 59
        assert tuple(row["goal_id"] for row in report["goals"]) == (
            FORMAL_GOAL_IDS
        )
        residual = (
            fixture.dense @ fixture.shadow_exact_values
            - fixture.dense @ fixture.current_values
        )
        for row in report["goals"]:
            goal_id = row["goal_id"]
            gradient = fixture.gradient_values[goal_id]
            adjoint = np.linalg.solve(
                fixture.dense.conj().T,
                gradient,
            )
            expected_eta = float(np.vdot(adjoint, residual).real)
            assert result.signed_eta[goal_id] == pytest.approx(
                expected_eta,
                rel=2.0e-11,
                abs=2.0e-12,
            )
            assert (
                row["adjoint_true_relative_residual"] <= 1.0e-9
            )
            assert len(row["goal_evidence_sha256"]) == 64
        assert report["algebra"]["endpoint_goal_delta_consumed"] is False
        assert report["algebra"]["reference_solution_consumed"] is False
        assert (
            report["capability_credit"]["actual_signed_dwr_complete"]
            is True
        )
        implementation = dict(report["implementation_identity"])
        implementation_sha = implementation.pop(
            "implementation_sha256"
        )
        assert len(implementation_sha) == 64
        assert (
            report["aggregate_identities"]["implementation_sha256"]
            == implementation_sha
        )
        assert len(
            report["aggregate_identities"]["primal_residual_sha256"]
        ) == 64
        assert len(
            report["aggregate_identities"]["adjoint_system_sha256"]
        ) == 64
        for name in (
            "goal_gradient_construction_complete",
            "current_to_shadow_injection_complete",
            "local_h_transfer_complete",
            "shadow_endpoint_effectivity_complete",
            "accuracy_credit",
        ):
            assert report["capability_credit"][name] is False
        assert len(result.report_sha256) == 64
        observed = {
            "matrix": int(fixture.matrix.stateGet()),
            "rhs": int(fixture.rhs.stateGet()),
            "shadow": int(fixture.shadow_solution.stateGet()),
            "current": int(fixture.current.stateGet()),
            **{
                goal_id: int(vector.stateGet())
                for goal_id, vector in fixture.gradients.items()
            },
        }
        assert observed == protected
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial actual-DWR component test",
)
def test_actual_dwr_rejects_incomplete_goal_inventory_and_bad_gate(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "shadow-plan.json"
    plan_sha = _write_plan(plan_path)
    fixture = _Fixture(plan_path, plan_sha, comm=MPI.COMM_WORLD)
    try:
        missing = dict(fixture.gradients)
        missing.pop(FORMAL_GOAL_IDS[-1])
        with pytest.raises(
            Task035eActualDWRError,
            match="goal-gradient inventory",
        ):
            evaluate_task035e_actual_dwr(
                fixture.view,
                fixture.current,
                missing,
                source_sha=SOURCE_SHA,
                expected_shadow_plan_sha256=plan_sha,
                shadow_kind="h-shadow",
            )
        fixture.view.full_active_residual[
            "linear_system_relative_residual"
        ] = 2.0e-8
        with pytest.raises(
            Task035eActualDWRError,
            match="qualified primal/port Gate",
        ):
            _evaluate(fixture, plan_sha)
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial actual-DWR component test",
)
def test_actual_dwr_rejects_plan_source_and_layout_drift(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "shadow-plan.json"
    plan_sha = _write_plan(plan_path, source_sha="9" * 40)
    fixture = _Fixture(plan_path, plan_sha, comm=MPI.COMM_WORLD)
    try:
        with pytest.raises(
            Task035eActualDWRError,
            match="provenance source",
        ):
            _evaluate(fixture, plan_sha)
        plan_sha = _write_plan(plan_path)
        fixture.view.mesh_data.local_h_context.plan_file_sha256 = plan_sha
        wrong = _vector_from_global(
            np.ones(fixture.size + 1, dtype=np.complex128),
            MPI.COMM_WORLD,
        )
        try:
            with pytest.raises(
                Task035eActualDWRError,
                match="layout",
            ):
                evaluate_task035e_actual_dwr(
                    fixture.view,
                    wrong,
                    fixture.gradients,
                    source_sha=SOURCE_SHA,
                    expected_shadow_plan_sha256=plan_sha,
                    shadow_kind="p-shadow",
                )
        finally:
            wrong.destroy()
    finally:
        fixture.destroy()


def test_actual_dwr_source_contains_no_python_vector_allgather() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "adaptivity"
        / "task035e_actual_dwr.py"
    ).read_text(encoding="utf-8")
    assert ".allgather(" not in source
    assert ".gather(" not in source
    assert "getValuesCSR" in source
    assert "solveTranspose" in source
    assert "multHermitian" in source


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8
    or os.environ.get("MYFENICS_RUN_TASK035E_ACTUAL_DWR_MPI8") != "1",
    reason="opt-in lightweight MPI8 actual-DWR fixture",
)
def test_opt_in_mpi8_actual_dwr() -> None:
    comm = MPI.COMM_WORLD
    root_path = None
    if comm.rank == 0:
        import tempfile

        root_path = tempfile.mkdtemp(
            prefix="task035e-actual-dwr-mpi8-",
            dir="/tmp",
        )
    shared = Path(comm.bcast(root_path, root=0))
    plan_path = shared / "shadow-plan.json"
    if comm.rank == 0:
        plan_sha = _write_plan(plan_path)
    else:
        plan_sha = None
    plan_sha = comm.bcast(plan_sha, root=0)
    comm.Barrier()
    fixture = _Fixture(plan_path, plan_sha, comm=comm)
    try:
        result = _evaluate(fixture, plan_sha)
        assert len(result.signed_eta) == 59
        assert max(
            row["adjoint_true_relative_residual"]
            for row in result.report["goals"]
        ) <= 1.0e-9
        assert (
            result.report["operator_identity"]["matrix"][
                "full_matrix_serialized"
            ]
            is False
        )
        digest_prefix = int(result.report_sha256[:15], 16)
        assert comm.allreduce(digest_prefix, op=MPI.MIN) == (
            comm.allreduce(digest_prefix, op=MPI.MAX)
        )
    finally:
        fixture.destroy()
        comm.Barrier()
        if comm.rank == 0:
            shutil.rmtree(shared)
        comm.Barrier()
