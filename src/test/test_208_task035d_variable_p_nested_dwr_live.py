from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from benchmarks.task035d_nested_p_dwr_checker import (
    task035d_nested_p_dwr_report_gate,
)
from src.adaptivity import variable_p_nested_dwr as live_dwr
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d


ROOT = Path(__file__).resolve().parents[2]
CHANNEL_AUTHORITY = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "significant_channel_reference_v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _petsc_system(
    dense: np.ndarray,
    rhs_values: np.ndarray,
) -> tuple[PETSc.Mat, PETSc.Vec, PETSc.Vec, PETSc.KSP]:
    matrix = PETSc.Mat().createAIJ(
        size=dense.shape,
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    start, end = map(int, matrix.getOwnershipRange())
    for row in range(start, end):
        columns = np.flatnonzero(np.abs(dense[row]) > 0.0)
        matrix.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray(columns, dtype=PETSc.IntType),
            np.asarray(
                dense[row, columns].reshape(1, -1),
                dtype=PETSc.ScalarType,
            ),
        )
    matrix.assemble()
    rhs = PETSc.Vec().createMPI(len(rhs_values), comm=MPI.COMM_WORLD)
    owned_start, owned_end = map(int, rhs.getOwnershipRange())
    rhs.getArray()[:] = rhs_values[owned_start:owned_end]
    rhs.assemble()
    state = rhs.duplicate()
    solver = PETSc.KSP().create(MPI.COMM_WORLD)
    solver.setType(PETSc.KSP.Type.PREONLY)
    solver.getPC().setType(PETSc.PC.Type.LU)
    solver.getPC().setFactorSolverType("mumps")
    solver.setOperators(matrix)
    solver.setErrorIfNotConverged(True)
    solver.solve(rhs, state)
    assert solver.getConvergedReason() > 0
    return matrix, rhs, state, solver


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    return np.concatenate(
        MPI.COMM_WORLD.allgather(
            np.asarray(
                vector.getArray(readonly=True),
                dtype=np.complex128,
            ).copy()
        )
    )


def _dense_system(
    *,
    enriched: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    size = 2 + len(modes)
    schur_b = np.asarray(
        [[3.2 + 0.11j, -0.12 + 0.04j], [0.08j, 2.9 - 0.07j]],
        dtype=np.complex128,
    )
    schur_a = schur_b + np.asarray(
        [[0.31 - 0.05j, 0.04j], [-0.025 + 0.01j, -0.22 + 0.03j]],
        dtype=np.complex128,
    )
    matrix = np.diag(
        2.5 + 0.003 * np.arange(size) + 0.04j
    ).astype(np.complex128)
    matrix[:2, :2] = schur_a if enriched else schur_b
    for index in range(len(modes)):
        auxiliary = 2 + index
        trace = index % 2
        matrix[trace, auxiliary] = (
            0.004 * np.cos(0.13 * (index + 1.0))
            + 0.003j * np.sin(0.07 * (index + 1.0))
        )
        matrix[auxiliary, trace] = (
            -0.002 * np.sin(0.09 * (index + 1.0))
            + 0.0035j * np.cos(0.11 * (index + 1.0))
        )
    rows = np.arange(size, dtype=np.float64)
    rhs = (
        0.2 * np.cos(0.17 * (rows + 1.0))
        + 0.13j * np.sin(0.19 * (rows + 1.0))
    ).astype(np.complex128)
    return matrix, rhs, schur_a if enriched else schur_b


def _port_operator_audit_fixture() -> dict[str, object]:
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
        "trace_functional_count": 2,
        "removed_active_interior_max_abs": 0.0,
        "removed_active_interior_over_threshold_max": 0.0,
        "acceptance_threshold_max_abs": 1.0e-12,
        "auxiliary_interior_columns_allocated": False,
        "interior_degree_may_affect_port_operator": False,
        "external_operator_content_sha256": "e" * 64,
        "external_rhs_content_sha256": "f" * 64,
        "base_reduced_rhs_l2_norm": 0.0,
        "content_identity_is_partition_bound": True,
        "content_identity_requires_same_mpi_ownership": True,
    }


def _view(
    *,
    role: str,
    matrix: PETSc.Mat,
    rhs: PETSc.Vec,
    state: PETSc.Vec,
    solver: PETSc.KSP,
    schur: np.ndarray,
):
    config = target_stage4_config(degree=2, h_nm=50.0)
    modes = outgoing_port_modes_3d(config)
    state_values = _global_values(state)
    cell = SimpleNamespace(
        local_cell=0,
        global_cell=0,
        cell_info=0,
        trace_rows=np.asarray([0, 1], dtype=np.int64),
        degree_map=SimpleNamespace(
            signature="trace-p5-interior-p6"
            if role == "A"
            else "trace-p5-interior-p5"
        ),
    )
    recovery = SimpleNamespace(
        cell=cell,
        class_key=(f"fixture-{role}", cell.degree_map.signature, 0),
    )
    constrained = SimpleNamespace(
        local_cell=0,
        global_cell=0,
        canonical_leaf=0,
        independent_rows=np.asarray([0, 1], dtype=np.int64),
        full_trace_from_independent=np.eye(2, dtype=np.complex128),
    )
    system = SimpleNamespace(
        role=role,
        schur=schur,
        cell_recovery=(recovery,),
        trace_constraints=SimpleNamespace(
            owned_cells=(constrained,),
            audit={"schema_version": "fixture", "pass": True},
        ),
        active_trace_rows=2,
        appended_rows=len(modes),
    )
    return SimpleNamespace(
        role=role,
        A=matrix,
        b=rhs,
        x=state,
        ksp=solver,
        config=config,
        floquet_data=SimpleNamespace(
            phase_x=np.exp(0.2j),
            phase_y=np.exp(-0.3j),
        ),
        mesh_data=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_WORLD),
        ),
        reduction=SimpleNamespace(
            system=system,
            degree_plan=SimpleNamespace(audit={"fixture": role}),
            build_audit={
                "actual_full3d_equivalent_active_fe_dofs": (
                    200 if role == "A" else 180
                )
            },
        ),
        recovered=SimpleNamespace(
            active_full_rhs=None,
            active_auxiliary_interior_action=None,
        ),
        goal_context={
            "num_fem_dofs_after_mpc": 2,
            "modes": modes,
            "auxiliary_values": state_values[2:].copy(),
            "incident_projections": np.zeros(
                len(modes),
                dtype=np.complex128,
            ),
            "normalization": (
                "finite-port outgoing modal power / incident power"
            ),
        },
        full_active_residual={
            "linear_system_relative_residual": 1.0e-15,
        },
        primal_solver_telemetry={
            "converged_reason": int(solver.getConvergedReason()),
            "relative_residual": 1.0e-15,
        },
        port_metrics={"fixture": True},
        port_operator_audit=_port_operator_audit_fixture(),
    )


def _patch_live_geometry(monkeypatch) -> None:
    def same_trace_identity(view):
        start, end = map(int, view.x.getOwnershipRange())
        ranges = MPI.COMM_WORLD.allgather((start, end))
        layout = {
            "canonical_leaf": 0,
            "canonical_leaf_key": [0, 0, 0, 0, 0],
            "box": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
            "material_tag": 1,
            "local_cell": 0,
            "global_cell": 0,
            "cell_info": 0,
            "expansion_sha256": "a" * 64,
            "trace_layout_sha256": "b" * 64,
            "trace_rows": np.asarray([0, 1], dtype=np.int64),
            "independent_rows": np.asarray([0, 1], dtype=np.int64),
            "expansion": np.eye(2, dtype=np.complex128),
        }
        identity = {
            "schema_version": "fixture.same-trace.v1",
            "same_trace_identity_sha256": "c" * 64,
            "mpi_size": MPI.COMM_WORLD.size,
            "matrix_vector_ownership_ranges": [
                list(values) for values in ranges
            ],
        }
        return identity, (layout,)

    def candidate_identity(
        view,
        *,
        candidate_id,
        expected_plan_sha256,
        source_sha,
    ):
        return {
            "candidate_id": candidate_id,
            "source_sha": source_sha,
            "plan_file_sha256": expected_plan_sha256,
            "cell_interior_degree_sha256": (
                "a" * 64 if view.role == "A" else "b" * 64
            ),
            "actual_full3d_equivalent_active_fe_dofs": (
                200 if view.role == "A" else 180
            ),
        }

    def actions(
        system,
        *,
        reduced_trace_values=None,
        local_trace_values_by_global_cell=None,
    ):
        if reduced_trace_values is not None:
            trace = _global_values(reduced_trace_values)[:2]
        else:
            trace = np.asarray(
                local_trace_values_by_global_cell[0],
                dtype=np.complex128,
            )
        action = SimpleNamespace(
            local_cell=0,
            global_cell=0,
            cell_info=0,
            degree_signature=(
                "trace-p5-interior-p6"
                if system.role == "A"
                else "trace-p5-interior-p5"
            ),
            trace_rows=np.asarray([0, 1], dtype=np.int64),
            local_trace_values=trace.copy(),
            local_condensed_action=system.schur @ trace,
        )
        return (action,), {"pass": True, "fixture": True}

    monkeypatch.setattr(
        live_dwr,
        "_same_trace_identity",
        same_trace_identity,
    )
    monkeypatch.setattr(
        live_dwr,
        "_candidate_identity",
        candidate_identity,
    )
    monkeypatch.setattr(
        live_dwr,
        "retained_variable_p_owned_cell_schur_actions",
        actions,
    )
    monkeypatch.setattr(
        live_dwr,
        "_cell_rhs_corrections",
        lambda _view: {0: np.zeros(2, dtype=np.complex128)},
    )


def test_significant_authority_expands_to_36_real_goals() -> None:
    authority = live_dwr.load_significant_channel_authority(
        CHANNEL_AUTHORITY,
        expected_sha256=_sha256(CHANNEL_AUTHORITY),
    )
    assert len(authority.channels) == 12
    assert len(authority.goals) == 36
    assert sum(goal.quantity == "power" for goal in authority.goals) == 12
    assert len({goal.label for goal in authority.goals}) == 36


def test_primal_residual_gate_requires_reduced_and_full_explicit() -> None:
    passed = live_dwr._primal_residual_gate(
        full_active_residual={
            "linear_system_relative_residual": 2.0e-12
        },
        reduced_relative_residual=3.0e-12,
    )
    assert passed["pass"] is True

    failed = live_dwr._primal_residual_gate(
        full_active_residual={
            "linear_system_relative_residual": 2.0e-8
        },
        reduced_relative_residual=3.0e-12,
    )
    assert failed["pass"] is False
    assert failed["checks"][
        "full_explicit_true_relative_residual_le_1e-9"
    ] is False


@pytest.mark.parametrize(
    "field",
    (
        "external_operator_content_sha256",
        "external_rhs_content_sha256",
    ),
)
def test_port_operator_identity_rejects_content_hash_drift(
    field: str,
) -> None:
    common = _port_operator_audit_fixture()
    assert live_dwr._same_trace_port_operator_gate(
        common,
        common,
    )["pass"] is True
    drifted = dict(common)
    drifted[field] = "c" * 64
    gate = live_dwr._same_trace_port_operator_gate(
        common,
        drifted,
    )
    assert gate["pass"] is False
    assert gate["checks"][f"same_{field}"] is False


def test_port_operator_identity_rejects_unqualified_roundoff() -> None:
    common = _port_operator_audit_fixture()
    drifted = dict(common)
    drifted["removed_active_interior_over_threshold_max"] = 1.01
    gate = live_dwr._same_trace_port_operator_gate(common, drifted)
    assert gate["pass"] is False
    assert gate["checks"][
        "coarse_scale_aware_trace_roundoff"
    ] is False


def test_wrong_cell_attribution_is_not_absorbed_as_external() -> None:
    effective = np.asarray([1.0 + 0.0j, 0.0j])
    zero = np.zeros(2, dtype=np.complex128)
    audit, unexplained = live_dwr._vector_partition_audit(
        effective=effective,
        components={
            "coarse_solver_residual": zero,
            "cell_total": np.asarray([0.5 + 0.0j, 0.0j]),
            "port": zero,
            "auxiliary": zero,
            "enriched_solver_correction": zero,
        },
    )
    assert audit["pass"] is False
    np.testing.assert_allclose(
        unexplained,
        np.asarray([0.5 + 0.0j, 0.0j]),
    )
    assert audit["unexplained_residual_added_back_as_component"] is False


def test_rank_local_cell_validation_failure_is_collective(
    monkeypatch,
) -> None:
    def fail_only_on_rank_zero(**_kwargs):
        if MPI.COMM_WORLD.rank == 0:
            raise ValueError("rank-zero cell identity sentinel")
        return (
            [],
            np.zeros(1, dtype=np.complex128),
            {},
        )

    monkeypatch.setattr(
        live_dwr,
        "_validate_and_pair_cells_local",
        fail_only_on_rank_zero,
    )
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_WORLD)
        )
    )
    with pytest.raises(
        RuntimeError,
        match="rank-zero cell identity sentinel",
    ):
        live_dwr._validate_and_pair_cells(
            view=view,
            snapshot=None,
            layouts=(),
            actions_a=(),
            rhs_corrections_a={},
        )


def test_rank_local_shard_load_failure_is_collective(
    monkeypatch,
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-divergent shard failure fixture requires MPI2")
    shared_path = MPI.COMM_WORLD.bcast(
        str(tmp_path / "manifest.json")
        if MPI.COMM_WORLD.rank == 0
        else None,
        root=0,
    )
    manifest_path = Path(shared_path)
    source_sha = "d" * 40
    authority_sha = "e" * 64
    payload = {
        "schema_version": (
            "task035d.variable-p-nested-coarse-snapshot.v1"
        ),
        "pass": True,
        "role": "coarse_B",
        "same_trace_identity": {"mpi_size": 2},
        "candidate": {"source_sha": source_sha},
        "significant_channel_authority": {
            "sha256": authority_sha
        },
        "shards": [
            {
                "rank": rank,
                "path": f"rank{rank:04d}.npz",
                "sha256": str(rank) * 64,
                "ownership_range": [rank, rank + 1],
            }
            for rank in range(2)
        ],
    }
    if MPI.COMM_WORLD.rank == 0:
        manifest_path.write_text(
            live_dwr.json.dumps(payload) + "\n",
            encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    manifest_sha = MPI.COMM_WORLD.bcast(
        _sha256(manifest_path)
        if MPI.COMM_WORLD.rank == 0
        else None,
        root=0,
    )

    def rank_divergent_load(
        _path,
        *,
        expected_sha256,
        rank,
        mpi_size,
    ):
        del expected_sha256, mpi_size
        if rank == 0:
            raise ValueError("rank-zero shard sentinel")
        zero = np.zeros(1, dtype=np.complex128)
        return (
            {
                "ownership_range": np.asarray([1, 2]),
                "state_b_owned": zero,
                "rhs_b_owned": zero,
                "matrix_action_b_on_b_owned": zero,
                "residual_b_owned": zero,
            },
            (),
        )

    monkeypatch.setattr(
        live_dwr,
        "_load_rank_shard",
        rank_divergent_load,
    )
    with pytest.raises(
        RuntimeError,
        match="rank-zero shard sentinel",
    ):
        live_dwr.load_variable_p_nested_coarse_snapshot(
            manifest_path,
            communicator=MPI.COMM_WORLD,
            expected_manifest_sha256=manifest_sha,
            expected_source_sha=source_sha,
            expected_significant_channel_authority_sha256=(
                authority_sha
            ),
        )
    MPI.COMM_WORLD.barrier()


def test_rank_local_manifest_header_failure_is_collective(
    monkeypatch,
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-divergent manifest fixture requires MPI2")
    shared_path = MPI.COMM_WORLD.bcast(
        str(tmp_path / "header_manifest.json")
        if MPI.COMM_WORLD.rank == 0
        else None,
        root=0,
    )
    manifest_path = Path(shared_path)
    source_sha = "d" * 40
    authority_sha = "e" * 64
    payload = {
        "schema_version": (
            "task035d.variable-p-nested-coarse-snapshot.v1"
        ),
        "pass": True,
        "role": "coarse_B",
        "same_trace_identity": {"mpi_size": 2},
        "candidate": {"source_sha": source_sha},
        "significant_channel_authority": {
            "sha256": authority_sha
        },
        "shards": [
            {
                "rank": rank,
                "path": f"rank{rank:04d}.npz",
                "sha256": str(rank) * 64,
                "ownership_range": [rank, rank + 1],
            }
            for rank in range(2)
        ],
    }
    if MPI.COMM_WORLD.rank == 0:
        manifest_path.write_text(
            live_dwr.json.dumps(payload) + "\n",
            encoding="utf-8",
        )
    MPI.COMM_WORLD.barrier()
    expected_sha = MPI.COMM_WORLD.bcast(
        _sha256(manifest_path)
        if MPI.COMM_WORLD.rank == 0
        else None,
        root=0,
    )
    original_sha = live_dwr._file_sha256

    def fail_rank_zero_manifest(path):
        if (
            MPI.COMM_WORLD.rank == 0
            and Path(path) == manifest_path
        ):
            raise OSError("rank-zero manifest read sentinel")
        return original_sha(Path(path))

    monkeypatch.setattr(
        live_dwr,
        "_file_sha256",
        fail_rank_zero_manifest,
    )
    with pytest.raises(
        RuntimeError,
        match="rank-zero manifest read sentinel",
    ):
        live_dwr.load_variable_p_nested_coarse_snapshot(
            manifest_path,
            communicator=MPI.COMM_WORLD,
            expected_manifest_sha256=expected_sha,
            expected_source_sha=source_sha,
            expected_significant_channel_authority_sha256=(
                authority_sha
            ),
        )
    MPI.COMM_WORLD.barrier()


def test_rank_local_authority_failure_is_collective(
    monkeypatch,
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-divergent authority fixture requires MPI2")

    def rank_divergent_authority(*_args, **_kwargs):
        if MPI.COMM_WORLD.rank == 0:
            raise OSError("rank-zero authority read sentinel")
        return object()

    monkeypatch.setattr(
        live_dwr,
        "load_significant_channel_authority",
        rank_divergent_authority,
    )
    view = SimpleNamespace(
        mesh_data=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_WORLD)
        )
    )
    with pytest.raises(
        RuntimeError,
        match="rank-zero authority read sentinel",
    ):
        live_dwr.write_variable_p_nested_coarse_snapshot(
            view,
            artifact_directory=tmp_path / "must_not_write",
            candidate_id="fixture",
            expected_plan_sha256="1" * 64,
            source_sha="d" * 40,
            significant_channel_authority_path=CHANNEL_AUTHORITY,
            significant_channel_authority_sha256="e" * 64,
        )
    MPI.COMM_WORLD.barrier()


def test_rank_local_petsc_extraction_failure_is_collective() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-divergent PETSc extraction requires MPI2")

    class RankDivergentVector:
        def getComm(self):
            if MPI.COMM_WORLD.rank == 0:
                raise RuntimeError("rank-zero PETSc extraction sentinel")
            return PETSc.COMM_WORLD

        def getOwnershipRange(self):
            return MPI.COMM_WORLD.rank, MPI.COMM_WORLD.rank + 1

        def getArray(self, *, readonly):
            assert readonly is True
            return np.zeros(1, dtype=np.complex128)

        def getSize(self):
            return MPI.COMM_WORLD.size

    with pytest.raises(
        RuntimeError,
        match="rank-zero PETSc extraction sentinel",
    ):
        live_dwr._global_petsc_values(
            RankDivergentVector(),
            MPI.COMM_WORLD,
        )
    MPI.COMM_WORLD.barrier()


def test_rank_local_json_verification_failure_is_collective(
    monkeypatch,
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("rank-divergent JSON verification requires MPI2")
    shared_path = MPI.COMM_WORLD.bcast(
        str(tmp_path / "collective.json")
        if MPI.COMM_WORLD.rank == 0
        else None,
        root=0,
    )
    output = Path(shared_path)
    original_sha = live_dwr._file_sha256

    def fail_rank_zero_verification(path):
        if MPI.COMM_WORLD.rank == 0 and Path(path) == output:
            raise OSError("rank-zero JSON verification sentinel")
        return original_sha(Path(path))

    monkeypatch.setattr(
        live_dwr,
        "_file_sha256",
        fail_rank_zero_verification,
    )
    with pytest.raises(
        RuntimeError,
        match="rank-zero JSON verification sentinel",
    ):
        live_dwr._collective_publish_json(
            MPI.COMM_WORLD,
            output,
            {"fixture": True},
        )
    MPI.COMM_WORLD.barrier()


def test_serial_live_snapshot_and_36_goal_dwr_roundtrip(
    monkeypatch,
    tmp_path,
) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("dense live nested-p oracle is a serial fixture")
    _patch_live_geometry(monkeypatch)
    authority_sha = _sha256(CHANNEL_AUTHORITY)
    source_sha = "d" * 40
    matrix_b_dense, rhs_values, schur_b = _dense_system(enriched=False)
    matrix_a_dense, _, schur_a = _dense_system(enriched=True)
    matrix_b, rhs_b, state_b, solver_b = _petsc_system(
        matrix_b_dense,
        rhs_values,
    )
    matrix_a, rhs_a, state_a, solver_a = _petsc_system(
        matrix_a_dense,
        rhs_values,
    )
    view_b = _view(
        role="B",
        matrix=matrix_b,
        rhs=rhs_b,
        state=state_b,
        solver=solver_b,
        schur=schur_b,
    )
    view_a = _view(
        role="A",
        matrix=matrix_a,
        rhs=rhs_a,
        state=state_a,
        solver=solver_a,
        schur=schur_a,
    )
    try:
        snapshot_report = (
            live_dwr.write_variable_p_nested_coarse_snapshot(
                view_b,
                artifact_directory=tmp_path / "coarse",
                candidate_id="fixture_coarse_B",
                expected_plan_sha256="1" * 64,
                source_sha=source_sha,
                significant_channel_authority_path=CHANNEL_AUTHORITY,
                significant_channel_authority_sha256=authority_sha,
            )
        )
        assert snapshot_report["pass"] is True
        manifest_path = Path(snapshot_report["manifest_path"])
        loaded = live_dwr.load_variable_p_nested_coarse_snapshot(
            manifest_path,
            communicator=MPI.COMM_WORLD,
            expected_manifest_sha256=(
                snapshot_report["manifest_sha256"]
            ),
            expected_source_sha=source_sha,
            expected_significant_channel_authority_sha256=authority_sha,
        )
        np.testing.assert_allclose(
            loaded.state_b,
            _global_values(state_b),
            rtol=0.0,
            atol=0.0,
        )
        assert len(loaded.cells) == 1
        dwr_report = (
            live_dwr.evaluate_variable_p_nested_enriched_snapshot(
                view_a,
                coarse_manifest_path=manifest_path,
                coarse_manifest_sha256=(
                    snapshot_report["manifest_sha256"]
                ),
                artifact_path=tmp_path / "enriched" / "dwr.json",
                candidate_id="fixture_enriched_A",
                expected_plan_sha256="2" * 64,
                source_sha=source_sha,
                significant_channel_authority_path=CHANNEL_AUTHORITY,
                significant_channel_authority_sha256=authority_sha,
            )
        )
        assert dwr_report["pass"] is True
        payload = live_dwr.json.loads(
            Path(dwr_report["report_path"]).read_text(encoding="utf-8")
        )
        assert payload["residual_partition"]["pass"] is True
        assert payload["primal_endpoints"][
            "coarse_residual_gate"
        ]["pass"] is True
        assert payload["primal_endpoints"][
            "enriched_residual_gate"
        ]["pass"] is True
        assert payload["significant_channel_authority"][
            "selected_goal_set_complete_by_frozen_authority"
        ] is True
        assert payload["unit_channel_adjoint_basis"]["pass"] is True
        assert payload["unit_channel_adjoint_basis"][
            "unit_adjoint_solve_count"
        ] == 12
        assert payload["goal_dwr"]["passed_real_goal_count"] == 36
        assert payload["goal_dwr"]["power_goal_pass_count"] == 12
        assert (
            payload["goal_dwr"][
                "complex_amplitude_component_goal_pass_count"
            ]
            == 24
        )
        assert payload["cell_residuals"][
            "interior_degree_changed_cell_count"
        ] == 1
        assert payload["external_partition"][
            "zero_delta_derived_from_independent_port_identity"
        ] is True
        assert payload["external_partition"]["port_l2_norm"] == 0.0
        assert payload["external_partition"]["auxiliary_l2_norm"] == 0.0
        formalized_payload = deepcopy(payload)
        for goal in formalized_payload["goal_dwr"]["goals"].values():
            goal["cell_contributions"].extend(
                {
                    "canonical_leaf": leaf,
                    "complex_pairing": [0.0, 0.0],
                }
                for leaf in range(1, 134)
            )
        base_cell = formalized_payload["cell_residuals"][
            "records"
        ][0]
        formalized_payload["cell_residuals"]["records"] = [
            {
                **deepcopy(base_cell),
                "canonical_leaf": leaf,
                "interior_degree_changed": leaf < 32,
            }
            for leaf in range(134)
        ]
        formalized_payload["cell_residuals"][
            "global_cell_count"
        ] = 134
        formalized_payload["cell_residuals"][
            "interior_degree_changed_cell_count"
        ] = 32
        independent_gate = task035d_nested_p_dwr_report_gate(
            formalized_payload,
            live_dwr.json.loads(
                CHANNEL_AUTHORITY.read_text(encoding="utf-8")
            ),
        )
        assert independent_gate["pass"] is True, independent_gate

        original_actions = (
            live_dwr.retained_variable_p_owned_cell_schur_actions
        )

        def corrupted_actions(system, **kwargs):
            actions, audit = original_actions(system, **kwargs)
            if system.role != "A":
                return actions, audit
            corrupted = SimpleNamespace(**vars(actions[0]))
            corrupted.local_condensed_action = np.asarray(
                actions[0].local_condensed_action
            ).copy()
            corrupted.local_condensed_action[0] += 1.0e-3
            return (corrupted,), audit

        monkeypatch.setattr(
            live_dwr,
            "retained_variable_p_owned_cell_schur_actions",
            corrupted_actions,
        )
        negative_path = tmp_path / "negative" / "dwr.json"
        with pytest.raises(
            RuntimeError,
            match="residual partition failed",
        ):
            live_dwr.evaluate_variable_p_nested_enriched_snapshot(
                view_a,
                coarse_manifest_path=manifest_path,
                coarse_manifest_sha256=(
                    snapshot_report["manifest_sha256"]
                ),
                artifact_path=negative_path,
                candidate_id="fixture_enriched_A",
                expected_plan_sha256="2" * 64,
                source_sha=source_sha,
                significant_channel_authority_path=CHANNEL_AUTHORITY,
                significant_channel_authority_sha256=authority_sha,
            )
        negative = live_dwr.json.loads(
            negative_path.read_text(encoding="utf-8")
        )
        assert negative["pass"] is False
        assert negative["controlled_negative"] is True
        assert (
            negative["failure_stage"]
            == "residual_partition_before_adjoints"
        )
    finally:
        for petsc_object in (
            solver_a,
            state_a,
            rhs_a,
            matrix_a,
            solver_b,
            state_b,
            rhs_b,
            matrix_b,
        ):
            petsc_object.destroy()
