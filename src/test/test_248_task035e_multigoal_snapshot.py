from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from src.adaptivity.task035e_multigoal_snapshot import (
    SHARD_SCHEMA,
    SNAPSHOT_SCHEMA,
    Task035eSnapshotError,
    build_task035e_multigoal_snapshot_observer,
    load_task035e_multigoal_snapshot,
    write_task035e_multigoal_snapshot,
)


SOURCE_SHA = "a" * 40
FOREST_SHA = "b" * 64
DEGREE_SHA = "c" * 64


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_plan(path: Path, *, source_sha: str = SOURCE_SHA) -> str:
    payload = {
        "schema_version": (
            "task035e.stage4-multilevel-local-h-refinement-plan.v1"
        ),
        "status": "stage4_balanced_multilevel_local_h_plan",
        "variable_trace_from_cell_degrees": True,
        "expected_forest": {
            "leaf_catalog_sha256": FOREST_SHA,
        },
        "cell_interior_degree_plan_sha256": DEGREE_SHA,
        "provenance": {
            "schema_version": "task035e.blind-initial-provenance.v1",
            "status": "blind_initial_provenance_closed",
            "source_sha": source_sha,
            "path_id": "A",
        },
    }
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return _file_sha256(path)


def _vector(
    global_size: int,
    *,
    offset: float,
    comm: MPI.Intracomm,
) -> PETSc.Vec:
    vector = PETSc.Vec().createMPI(global_size, comm=comm)
    start, end = map(int, vector.getOwnershipRange())
    rows = np.arange(start, end, dtype=np.float64)
    vector.getArray()[:] = (
        offset
        + 0.13 * (rows + 1.0)
        + 0.07j * np.sin(0.2 * (rows + 1.0))
    )
    vector.assemble()
    return vector


def _matrix_and_state(
    comm: MPI.Intracomm,
) -> tuple[PETSc.Mat, PETSc.Vec, PETSc.Vec]:
    size = max(4, 2 * comm.size)
    matrix = PETSc.Mat().createAIJ(
        size=(size, size),
        nnz=3,
        comm=comm,
    )
    matrix.setUp()
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = [row]
        values = [3.0 + 0.02j * (row + 1)]
        if row > 0:
            columns.append(row - 1)
            values.append(-0.2 + 0.01j)
        if row + 1 < size:
            columns.append(row + 1)
            values.append(0.11 - 0.03j)
        matrix.setValues(
            [row],
            columns,
            np.asarray(values, dtype=PETSc.ScalarType).reshape(1, -1),
        )
    matrix.assemble()
    state = _vector(size, offset=0.25, comm=comm)
    rhs = matrix.createVecLeft()
    matrix.mult(state, rhs)
    return matrix, rhs, state


def _mode() -> SimpleNamespace:
    return SimpleNamespace(
        side="top",
        m=0,
        n=0,
        polarization="s",
        alpha=0.1 + 0.0j,
        gamma=0.0 + 0.0j,
        beta=0.7 + 0.02j,
        refractive_index=1.0 + 0.0j,
        vertical_sign=1,
        e_vector=np.asarray([0.0, 1.0, 0.0], dtype=np.complex128),
        k_vector=np.asarray(
            [0.1, 0.0, 0.7 + 0.02j], dtype=np.complex128
        ),
        h_vector=np.asarray(
            [-0.7 - 0.02j, 0.0, 0.1], dtype=np.complex128
        ),
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=0.4,
        propagating=True,
        rayleigh_warning=False,
    )


def _port_audit() -> dict[str, object]:
    checks = {
        "trace_functionals_present": True,
        "trace_only_gate": True,
        "removed_interior_is_qualified_roundoff": True,
        "no_auxiliary_interior_columns": True,
        "external_operator_content_hash": True,
        "external_rhs_content_hash": True,
        "zero_volume_base_rhs": True,
    }
    return {
        "schema_version": (
            "task035d.variable-p-trace-only-port-operator.v1"
        ),
        "pass": True,
        "checks": checks,
        "auxiliary_interior_columns_allocated": False,
        "external_operator_content_sha256": "d" * 64,
        "external_rhs_content_sha256": "e" * 64,
        "content_identity_is_partition_bound": True,
    }


class _Fixture:
    def __init__(
        self,
        plan_path: Path,
        plan_sha256: str,
        *,
        comm: MPI.Intracomm,
        auxiliary_action_present: bool,
    ) -> None:
        self.comm = comm
        self.matrix, self.rhs, self.state = _matrix_and_state(comm)
        self.active_solution = _vector(
            max(6, 3 * comm.size),
            offset=1.0,
            comm=comm,
        )
        self.active_rhs = _vector(
            self.active_solution.getSize(),
            offset=2.0,
            comm=comm,
        )
        self.active_auxiliary = (
            _vector(
                self.active_solution.getSize(),
                offset=0.01,
                comm=comm,
            )
            if auxiliary_action_present
            else None
        )
        self.p6 = _vector(
            max(8, 4 * comm.size),
            offset=-0.5,
            comm=comm,
        )
        field = SimpleNamespace(
            x=SimpleNamespace(petsc_vec=self.p6),
        )
        context = SimpleNamespace(
            plan_path=str(plan_path),
            plan_file_sha256=plan_sha256,
            forest=SimpleNamespace(
                audit={
                    "schema_version": "task035d.dyadic-hexa-forest.v1",
                    "pass": True,
                    "leaf_catalog_sha256": FOREST_SHA,
                    "leaf_cell_count": 8,
                }
            ),
        )
        entity_map = SimpleNamespace(
            active_rows=int(self.active_solution.getSize()),
            active_trace_rows=max(
                1, int(self.active_solution.getSize()) - 2
            ),
        )
        system = SimpleNamespace(
            entity_map=entity_map,
            active_trace_rows=max(1, self.state.getSize() - 1),
            appended_rows=1,
            build_audit={
                "schema_version": "fixture.variable-p-system.v1",
                "pass": True,
            },
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
                    "active_rows": entity_map.active_rows,
                }
            ),
            build_audit={
                "schema_version": (
                    "task035d.variable-p-assembly-reduction.v1"
                ),
                "actual_full3d_equivalent_active_fe_dofs": (
                    entity_map.active_rows - 1
                ),
                "inactive_p6_rows_globally_numbered": False,
            },
        )
        recovered = SimpleNamespace(
            field=field,
            active_full_solution=self.active_solution,
            active_full_rhs=self.active_rhs,
            active_auxiliary_interior_action=self.active_auxiliary,
            audit={
                "schema_version": (
                    "task035d.variable-p-solution-recovery.v2"
                ),
                "status": "variable_p_full_field_recovery_pass",
                "pass": True,
            },
        )
        self.view = SimpleNamespace(
            field=field,
            mesh_data=SimpleNamespace(
                mesh=SimpleNamespace(comm=comm),
                local_h_context=context,
            ),
            config=SimpleNamespace(
                as_jsonable=lambda: {
                    "case_name": "task035e_snapshot_fixture",
                    "stage_case": "stage4_block_grating",
                    "stage4_local_h_refinement_plan": str(plan_path),
                }
            ),
            floquet_data=SimpleNamespace(
                phase_x=np.exp(0.2j),
                phase_y=np.exp(-0.3j),
                phase_corner=np.exp(-0.1j),
                constraint_mode_resolved="topological_trace_p6",
                num_constraints=12,
                num_x_constraints=4,
                num_y_constraints=4,
                num_corner_constraints=4,
                used_full_boundary_gather=False,
                created_dense_boundary_square=False,
            ),
            A=self.matrix,
            b=self.rhs,
            x=self.state,
            reduction=reduction,
            recovered=recovered,
            goal_context={
                "num_fem_dofs_after_mpc": self.state.getSize() - 1,
                "modes": (_mode(),),
                "auxiliary_values": np.asarray(
                    [0.2 + 0.1j], dtype=np.complex128
                ),
                "incident_projections": np.asarray(
                    [0.0 + 0.0j], dtype=np.complex128
                ),
                "normalization": (
                    "finite-port outgoing modal power / incident power"
                ),
            },
            port_metrics={
                "R_total": 0.6,
                "T_total": 0.1,
                "A_balance": 0.3,
            },
            port_operator_audit=_port_audit(),
            full_active_residual={
                "linear_system_relative_residual": 2.0e-12,
                "full_explicit_true_residual_pass": True,
                "active_selected_rows": {
                    "selected_value_bytes_local": 64 + comm.rank,
                },
                "reduced_constraint_norm": {
                    "work_owned_component_count_local": comm.rank,
                },
            },
            primal_solver_telemetry={
                "converged_reason": 2,
                "iterations": 1,
                "ksp_type": "preonly",
                "pc_type": "lu",
                "pc_factor_solver_type": "mumps",
                "linear_system_relative_residual": 2.0e-12,
                "active_selected_rows": {
                    "selected_value_bytes_local": 64 + comm.rank,
                },
                "reduced_constraint_norm": {
                    "work_owned_component_count_local": comm.rank,
                },
            },
        )

    def destroy(self) -> None:
        for value in (
            self.active_auxiliary,
            self.p6,
            self.active_rhs,
            self.active_solution,
            self.state,
            self.rhs,
            self.matrix,
        ):
            if value is not None:
                value.destroy()


def _publish(
    fixture: _Fixture,
    artifact_directory: Path,
    plan_sha: str,
    *,
    allow_serial: bool,
):
    return write_task035e_multigoal_snapshot(
        fixture.view,
        artifact_directory=artifact_directory,
        source_sha=SOURCE_SHA,
        trial_id="trial-A",
        cycle_index=0,
        expected_plan_sha256=plan_sha,
        allow_serial_test_fixture=allow_serial,
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial component test",
)
def test_serial_snapshot_roundtrip_is_immutable_and_fail_closed(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_plan(plan_path)
    fixture = _Fixture(
        plan_path,
        plan_sha,
        comm=MPI.COMM_WORLD,
        auxiliary_action_present=False,
    )
    try:
        receipt = _publish(
            fixture,
            tmp_path / "snapshot",
            plan_sha,
            allow_serial=True,
        )
        loaded = load_task035e_multigoal_snapshot(
            receipt.manifest_path,
            expected_manifest_file_sha256=(
                receipt.manifest_file_sha256
            ),
        )
        manifest = loaded.manifest
        assert manifest["schema_version"] == SNAPSHOT_SCHEMA
        assert manifest["formal_mpi8_qualified"] is False
        assert manifest["diagnostic_serial_fixture"] is True
        assert manifest["no_full_vector_python_allgather"] is True
        assert manifest["matrix_operator"]["full_matrix_serialized"] is False
        assert (
            manifest["capability_credit"]["current_primal_snapshot_complete"]
            is True
        )
        for name in (
            "multi_goal_adjoint_complete",
            "dwr_complete",
            "local_h_transfer_complete",
            "shadow_effectivity_complete",
            "accuracy_credit",
        ):
            assert manifest["capability_credit"][name] is False
        assert (
            str(loaded.arrays["schema_version"][0]) == SHARD_SCHEMA
        )
        assert np.array_equal(
            loaded.arrays["reduced_residual_owned"],
            loaded.arrays["reduced_b_owned"]
            - loaded.arrays["reduced_ax_owned"],
        )
        assert np.count_nonzero(
            loaded.arrays["active_full_auxiliary_action_owned"]
        ) == 0
        assert not loaded.arrays["reduced_x_owned"].flags.writeable
        assert stat.S_IMODE(receipt.manifest_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(loaded.shard_path.stat().st_mode) == 0o600
        with np.load(loaded.shard_path, allow_pickle=False) as archive:
            assert not any("csr" in name.lower() for name in archive.files)

        os.chmod(loaded.shard_path, 0o644)
        with pytest.raises(ValueError, match="mode"):
            load_task035e_multigoal_snapshot(
                receipt.manifest_path,
                expected_manifest_file_sha256=(
                    receipt.manifest_file_sha256
                ),
            )
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial component test",
)
def test_snapshot_rejects_non_mpi8_without_explicit_test_scope(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_plan(plan_path)
    fixture = _Fixture(
        plan_path,
        plan_sha,
        comm=MPI.COMM_WORLD,
        auxiliary_action_present=False,
    )
    try:
        with pytest.raises(Task035eSnapshotError, match="MPI8"):
            _publish(
                fixture,
                tmp_path / "not-written",
                plan_sha,
                allow_serial=False,
            )
        assert not (tmp_path / "not-written").exists()
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial component test",
)
def test_snapshot_rejects_source_plan_and_port_gate_drift(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_plan(plan_path, source_sha="f" * 40)
    fixture = _Fixture(
        plan_path,
        plan_sha,
        comm=MPI.COMM_WORLD,
        auxiliary_action_present=False,
    )
    try:
        with pytest.raises(Task035eSnapshotError, match="source SHA"):
            _publish(
                fixture,
                tmp_path / "source-drift",
                plan_sha,
                allow_serial=True,
            )
        fixture.view.port_operator_audit["checks"][
            "trace_only_gate"
        ] = False
        fixture.view.port_operator_audit["pass"] = False
        _write_plan(plan_path, source_sha=SOURCE_SHA)
        plan_sha = _file_sha256(plan_path)
        fixture.view.mesh_data.local_h_context.plan_file_sha256 = plan_sha
        with pytest.raises(Task035eSnapshotError, match="port operator"):
            _publish(
                fixture,
                tmp_path / "port-drift",
                plan_sha,
                allow_serial=True,
            )
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial component test",
)
def test_observer_factory_publishes_the_same_narrow_artifact(
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_sha = _write_plan(plan_path)
    fixture = _Fixture(
        plan_path,
        plan_sha,
        comm=MPI.COMM_WORLD,
        auxiliary_action_present=True,
    )
    try:
        observer = build_task035e_multigoal_snapshot_observer(
            artifact_directory=tmp_path / "observer-snapshot",
            source_sha=SOURCE_SHA,
            trial_id="trial-observer",
            cycle_index=0,
            expected_plan_sha256=plan_sha,
            allow_serial_test_fixture=True,
        )
        assert observer(fixture.view) is None
        manifest = tmp_path / "observer-snapshot" / "manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert (
            payload["partitions"]["active_full"][
                "auxiliary_action_present"
            ]
            is True
        )
    finally:
        fixture.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8
    or os.environ.get("MYFENICS_RUN_TASK035E_SNAPSHOT_MPI8") != "1",
    reason="opt-in lightweight MPI8 snapshot fixture",
)
def test_opt_in_mpi8_snapshot_roundtrip() -> None:
    comm = MPI.COMM_WORLD
    root_path = None
    if comm.rank == 0:
        import tempfile

        root_path = tempfile.mkdtemp(
            prefix="task035e-multigoal-snapshot-mpi8-",
            dir="/tmp",
        )
    shared = Path(comm.bcast(root_path, root=0))
    plan_path = shared / "plan.json"
    if comm.rank == 0:
        plan_sha = _write_plan(plan_path)
    else:
        plan_sha = None
    plan_sha = comm.bcast(plan_sha, root=0)
    comm.Barrier()
    fixture = _Fixture(
        plan_path,
        plan_sha,
        comm=comm,
        auxiliary_action_present=True,
    )
    try:
        receipt = _publish(
            fixture,
            shared / "snapshot",
            plan_sha,
            allow_serial=False,
        )
        loaded = load_task035e_multigoal_snapshot(
            receipt.manifest_path,
            expected_manifest_file_sha256=(
                receipt.manifest_file_sha256
            ),
            communicator=comm,
        )
        assert receipt.formal_mpi8_qualified is True
        assert loaded.manifest["mpi_size"] == 8
        assert len(loaded.manifest["shards"]) == 8
        assert (
            loaded.manifest["partitions"]["reduced"]["global_size"]
            == fixture.state.getSize()
        )
        assert (
            loaded.manifest["matrix_operator"][
                "partition_bound_csr_sha256"
            ]
            and len(
                loaded.manifest["matrix_operator"][
                    "partition_bound_csr_sha256"
                ]
            )
            == 64
        )
    finally:
        fixture.destroy()
        comm.Barrier()
        if comm.rank == 0:
            shutil.rmtree(shared)
        comm.Barrier()
