"""Small Task42 direct-path contracts; no mesh, factorization, or PDE is built."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.dtn_port_3d as dtn
from scripts import run_case
from src.io.execution_plan import WORKER_MODULE, build_execution_plan
from src.runners import task038_full3d_direct, task038_input_worker, task038_launcher
from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverRequest
from src.solvers.full3d_lifecycle_packet import load_packet, write_packet
from src.solvers.petsc_lu_stage import (
    TASK42_STAGED_DIRECT_STAGE_IDENTITY,
    StagedMumpsLUFactory,
    load_lu_stage_bridge,
)


class _SerialCollective:
    rank = 0
    size = 1

    def __init__(self):
        self.calls = []

    @property
    def collective_count(self):
        return len(self.calls)

    def allreduce(self, value, op=None):
        self.calls.append(("allreduce", value))
        return value

    def allgather(self, value):
        self.calls.append(("allgather", value))
        return [value]

    def bcast(self, value, root=0):
        self.calls.append(("bcast", root))
        return value


class _Vector:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128)

    def getArray(self, readonly=False):
        return self.values

    def getOwnershipRange(self):
        return (0, self.values.size)


class _Factor:
    stage_identity = "task42.test.factor"
    numeric_ready = True

    def __init__(self):
        self.lifecycle = {"created": True, "numeric": True}
        self.analysis_info_raw = {"INFOG_api_raw_by_rank": []}
        self.numeric_info_raw = {"INFOG_api_raw_by_rank": []}
        self.destroy_calls = 0

    def destroy(self):
        self.destroy_calls += 1
        return {"factor_released": True, "destroy_error_code": 0}


def _residual(relative=1.0e-12):
    return {
        "linear_system_rhs_norm": 2.0,
        "linear_system_solution_norm": 1.0,
        "linear_system_residual_norm": 2.0 * relative,
        "linear_system_relative_residual": relative,
        "reduced_trace_dtn_residual_norm": 1.0e-12,
        "eliminated_cell_interior_residual_norm": 1.0e-12,
        "eliminated_cell_interior_max_abs_residual": 1.0e-12,
        "full_operator_residual_method": (
            "explicit reduced trace+DtN Mat action combined with matrix-free "
            "dolfinx_mpc UFL action projected onto every active eliminated "
            "cell-interior test space, including condensed full-space RHS"
        ),
        "full_global_matrix_allocated_for_residual": False,
        "full_trace_matrix_allocated_for_residual": False,
    }


def _strict_residual(relative=1.0e-12):
    """Match _task42_strict_linear_residual's smaller pre-recovery schema."""

    return {**_residual(relative), "finite": True}


class _DuplicateTrackingVector:
    def __init__(self, vector):
        self.vector = vector
        self.duplicate_calls = 0

    def getComm(self):
        return self.vector.getComm()

    def getSize(self):
        return self.vector.getSize()

    def getOwnershipRange(self):
        return self.vector.getOwnershipRange()

    def getArray(self, readonly=False):
        return self.vector.getArray(readonly=readonly)

    def duplicate(self):
        self.duplicate_calls += 1
        return self.vector.duplicate()


@pytest.mark.parametrize("defect", ["single_rank_shard_hash", "single_rank_local_layout"])
def test_task42_packet_restore_syncs_local_shard_rejection_before_vec_duplicate(
    tmp_path: Path, defect: str
) -> None:
    """One bad rank must refuse collectively before the collective VecDuplicate."""

    comm = MPI.COMM_WORLD
    if comm.size < 2:
        pytest.skip("single-rank shard rejection requires MPI2")
    shared_directory = Path(
        comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0)
    )
    if comm.rank == 0:
        shutil.rmtree(shared_directory, ignore_errors=True)
    comm.barrier()

    identity = {"source_sha": "task42-packet-recovery-test", "mpi_size": comm.size}
    mode = SimpleNamespace(side="top", m=0, n=0, polarization="s")
    vector = PETSc.Vec().createMPI((2, 2 * comm.size), comm=comm)
    vector_refcount_before = int(vector.getRefCount())
    try:
        vector.getArray()[:] = np.asarray(
            [1.0 + comm.rank * 1j, 2.0 - comm.rank * 1j],
            dtype=np.complex128,
        )
        ownership = tuple(int(value) for value in vector.getOwnershipRange())
        packet_write = write_packet(
            shared_directory,
            vector.getArray(readonly=True),
            vector.getArray(readonly=True),
            identity=identity,
            metadata={
                "external_keys": [
                    {"side": "top", "m": 0, "n": 0, "polarization": "s"}
                ],
                "external_q": [[0.0, 0.0]],
            },
            ownership_range=ownership,
            comm=comm,
            collective_writer_errors=True,
        )
        assert packet_write["pass"] is True

        manifest_path = shared_directory / "manifest.json"
        manifest_sha256 = None
        bad_rank = comm.size - 1
        if comm.rank == 0:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bad_shard = manifest["shards"][bad_rank]
            shard_path = shared_directory / bad_shard["path"]
            if defect == "single_rank_shard_hash":
                bad_shard["sha256"] = "0" * 64
            else:
                with np.load(shard_path, allow_pickle=False) as arrays:
                    bad_solution = arrays["solution"].copy()
                    bad_rhs = arrays["rhs"].copy()
                np.savez(
                    shard_path,
                    solution=np.concatenate((bad_solution, np.asarray([3.0j]))),
                    rhs=np.concatenate((bad_rhs, np.asarray([4.0j]))),
                )
                bad_shard["sha256"] = hashlib.sha256(
                    shard_path.read_bytes()
                ).hexdigest()
            manifest_bytes = (
                json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            manifest_path.write_bytes(manifest_bytes)
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_sha256 = comm.bcast(manifest_sha256, root=0)
        comm.barrier()

        tracked_vector = _DuplicateTrackingVector(vector)
        request = Stage4NeverMaterializedLinearSolverRequest(
            operator=SimpleNamespace(
                getSize=lambda: (2 * comm.size, 2 * comm.size),
                getOwnershipRange=lambda: ownership,
            ),
            b=tracked_vector,
            n_fe=2 * comm.size - 1,
            n_aux=1,
            static_condensed_system=SimpleNamespace(
                trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1})
            ),
            fine_operator=None,
            blocks=None,
            function_space=None,
            config=None,
            floquet_data=None,
            modes=(mode,),
        )
        recovery_port = dtn.task42_packet_recovery_port(
            manifest_path,
            manifest_sha256=manifest_sha256,
            identity=identity,
        )
        with pytest.raises(ValueError, match="Task42 packet restore rejected") as error:
            recovery_port(request)
        collective_errors = comm.allgather(str(error.value))
        assert len(set(collective_errors)) == 1
        vector_refcount_after = int(vector.getRefCount())
        refcount_rows = comm.allgather(
            {
                "rank": int(comm.rank),
                "before": vector_refcount_before,
                "after": vector_refcount_after,
            }
        )
        assert len(refcount_rows) == comm.size
        assert all(
            row["before"] == row["after"]
            for row in refcount_rows
        ), refcount_rows
        assert tracked_vector.duplicate_calls == 0
        if defect == "single_rank_shard_hash":
            assert f"rank_{bad_rank}:ValueError: pre-recovery shard hash mismatch" in str(
                error.value
            )
        else:
            assert f"rank_{bad_rank}:ValueError: pre-recovery ownership range mismatch" in str(
                error.value
            )
    finally:
        vector.destroy()
        comm.barrier()


def _write_small_task42_recovery_packet(tmp_path: Path, comm):
    packet_directory = Path(
        comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0)
    )
    if comm.rank == 0:
        shutil.rmtree(packet_directory, ignore_errors=True)
    comm.barrier()

    global_size = 4
    n_aux = 2
    n_fe = global_size - n_aux
    modes = (
        SimpleNamespace(side="top", m=0, n=0, polarization="s"),
        SimpleNamespace(side="bottom", m=1, n=0, polarization="p"),
    )
    operator = PETSc.Mat().createAIJ(
        size=(global_size, global_size), nnz=1, comm=comm
    )
    row_start, row_end = map(int, operator.getOwnershipRange())
    for row in range(row_start, row_end):
        operator.setValue(row, row, PETSc.ScalarType(2 + row + 1j * (row % 2)))
    operator.assemble()

    solution = operator.createVecRight()
    solution_start, solution_end = map(int, solution.getOwnershipRange())
    global_solution = np.asarray(
        [1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 1.0j, 4.0 - 0.5j],
        dtype=np.complex128,
    )
    solution.getArray()[:] = global_solution[solution_start:solution_end]
    rhs = operator.createVecLeft()
    operator.mult(solution, rhs)
    ownership = tuple(int(value) for value in rhs.getOwnershipRange())
    if tuple(solution.getOwnershipRange()) != ownership:
        raise AssertionError("small square action vector layouts differ")

    identity = {"source_sha": "task42-packet-recovery-positive-test", "mpi_size": comm.size}
    external_keys = dtn._pre_recovery_mode_keys(list(modes))
    external_values = global_solution[n_fe:]
    packet_write = write_packet(
        packet_directory,
        solution.getArray(readonly=True),
        rhs.getArray(readonly=True),
        identity=identity,
        metadata={
            "external_keys": external_keys,
            "external_q": [[float(value.real), float(value.imag)] for value in external_values],
        },
        ownership_range=ownership,
        comm=comm,
        collective_writer_errors=True,
    )
    assert packet_write["pass"] is True
    return {
        "operator": operator,
        "solution": solution,
        "rhs": rhs,
        "modes": modes,
        "n_fe": n_fe,
        "n_aux": n_aux,
        "identity": identity,
        "manifest_path": packet_directory / "manifest.json",
        "manifest_sha256": packet_write["manifest_sha256"],
    }


def test_task42_packet_recovery_restores_action_solution_without_factor(
    tmp_path: Path,
) -> None:
    comm = MPI.COMM_WORLD
    case = _write_small_task42_recovery_packet(tmp_path, comm)
    operator = case["operator"]
    solution = case["solution"]
    rhs = case["rhs"]
    restored_rhs = rhs.duplicate()
    snapshot = None
    try:
        tracked_rhs = _DuplicateTrackingVector(rhs)
        request = Stage4NeverMaterializedLinearSolverRequest(
            operator=operator,
            b=tracked_rhs,
            n_fe=case["n_fe"],
            n_aux=case["n_aux"],
            static_condensed_system=SimpleNamespace(
                trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1})
            ),
            fine_operator=None,
            blocks=None,
            function_space=None,
            config=None,
            floquet_data=None,
            modes=case["modes"],
        )
        snapshot = dtn.task42_packet_recovery_port(
            case["manifest_path"],
            manifest_sha256=case["manifest_sha256"],
            identity=case["identity"],
        )(request)
        assert snapshot.operation_kind == "task42_packet_recovery"
        assert snapshot.converged_reason is None
        assert snapshot.iterations is None
        assert snapshot.ksp_type == "not_run_packet_recovery"
        assert snapshot.pc_type == "not_run_packet_recovery"
        assert snapshot.recovery_evidence["global_factor_called"] is False
        assert snapshot.recovery_evidence["new_physical_solve_called"] is False
        assert tracked_rhs.duplicate_calls == 1
        assert np.array_equal(
            snapshot.x.getArray(readonly=True), solution.getArray(readonly=True)
        )

        operator.mult(snapshot.x, restored_rhs)
        restored_rhs.axpy(PETSc.ScalarType(-1), rhs)
        relative_residual = float(restored_rhs.norm()) / float(rhs.norm())
        assert relative_residual <= 5.0e-9
        assert dtn._external_snapshot_allows_official_rta(
            snapshot, relative_residual
        )
    finally:
        if snapshot is not None:
            snapshot.x.destroy()
        restored_rhs.destroy()
        solution.destroy()
        rhs.destroy()
        operator.destroy()
        comm.barrier()


@pytest.mark.parametrize("defect", ["rhs", "auxiliary_order"])
def test_task42_packet_recovery_rejects_rhs_or_auxiliary_order_mismatch(
    tmp_path: Path, defect: str
) -> None:
    comm = MPI.COMM_WORLD
    case = _write_small_task42_recovery_packet(tmp_path, comm)
    operator = case["operator"]
    solution = case["solution"]
    rhs = case["rhs"]
    try:
        if defect == "rhs" and comm.rank == 0 and rhs.getLocalSize():
            rhs.getArray()[0] += PETSc.ScalarType(0.125)
        modes = case["modes"]
        if defect == "auxiliary_order":
            modes = tuple(reversed(modes))
        tracked_rhs = _DuplicateTrackingVector(rhs)
        request = Stage4NeverMaterializedLinearSolverRequest(
            operator=operator,
            b=tracked_rhs,
            n_fe=case["n_fe"],
            n_aux=case["n_aux"],
            static_condensed_system=SimpleNamespace(
                trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1})
            ),
            fine_operator=None,
            blocks=None,
            function_space=None,
            config=None,
            floquet_data=None,
            modes=modes,
        )
        recovery_port = dtn.task42_packet_recovery_port(
            case["manifest_path"],
            manifest_sha256=case["manifest_sha256"],
            identity=case["identity"],
        )
        with pytest.raises(ValueError, match="Task42 packet restore rejected"):
            recovery_port(request)
        assert tracked_rhs.duplicate_calls == 0
    finally:
        solution.destroy()
        rhs.destroy()
        operator.destroy()
        comm.barrier()


def test_task42_packet_recovery_public_cli_plan_worker_adapter_binding(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    input_path = (
        Path(__file__).resolve().parents[2]
        / "input/official/task42hybrid_az90_50x50_17x20_0p7nm"
        / "13p5nm_p6h10_full3d_direct_mpi8.dat"
    )
    manifest_path = (tmp_path / "packet" / "manifest.json").resolve()
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    manifest_sha256 = "a" * 64
    run_directory = (tmp_path / "public-worker-run").resolve()
    captured: dict[str, object] = {}

    def fake_launch(specification, **kwargs):
        captured["launch_manifest"] = kwargs["task42_packet_recovery_manifest"]
        captured["launch_sha256"] = kwargs[
            "task42_packet_recovery_manifest_sha256"
        ]
        plan = build_execution_plan(
            specification,
            run_directory,
            source_sha="b" * 40,
            python_executable=sys.executable,
            mpiexec_command="mpiexec",
            task42_packet_recovery_manifest=kwargs[
                "task42_packet_recovery_manifest"
            ],
            task42_packet_recovery_manifest_sha256=kwargs[
                "task42_packet_recovery_manifest_sha256"
            ],
        )
        worker_start = plan.argv.index(WORKER_MODULE)
        worker_args = task038_input_worker._parser().parse_args(
            plan.argv[worker_start + 1 :]
        )
        assert worker_args.task42_packet_recovery_manifest == manifest_path
        assert (
            worker_args.task42_packet_recovery_manifest_sha256 == manifest_sha256
        )
        captured["plan_manifest"] = worker_args.task42_packet_recovery_manifest
        captured["plan_sha256"] = worker_args.task42_packet_recovery_manifest_sha256

        def stage_gate(*_args, **_kwargs):
            return True

        monkeypatch.setattr(
            task038_input_worker,
            "_task42_stage_gate_callback",
            lambda **_kwargs: stage_gate,
        )
        monkeypatch.setenv("TASK038_JOB_ROOT_PID", "12345")
        monkeypatch.delenv(
            task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV,
            raising=False,
        )

        def fake_direct_adapter(payload, directory, **adapter_kwargs):
            captured["adapter_model_id"] = payload["model_id"]
            captured["adapter_directory"] = directory
            captured["adapter_kwargs"] = adapter_kwargs
            return {"passed": True, "errors": []}

        monkeypatch.setattr(
            task038_full3d_direct, "run_full3d_direct", fake_direct_adapter
        )
        result = task038_input_worker._dispatch_resolved_payload(
            specification.as_jsonable(),
            expected_method=worker_args.expected_method,
            output_directory=worker_args.expected_output_directory,
            expected_source_sha=worker_args.expected_source_sha,
            expected_resolved_config_sha256=worker_args.resolved_config_sha256,
            task42_packet_recovery_manifest=(
                worker_args.task42_packet_recovery_manifest
            ),
            task42_packet_recovery_manifest_sha256=(
                worker_args.task42_packet_recovery_manifest_sha256
            ),
            comm=_SerialCollective(),
        )
        assert result == (0, [])
        adapter_kwargs = captured["adapter_kwargs"]
        assert adapter_kwargs["task42_bridge_path"] is None
        assert adapter_kwargs["task42_packet_recovery_manifest"] == manifest_path
        assert (
            adapter_kwargs["task42_packet_recovery_manifest_sha256"]
            == manifest_sha256
        )
        assert adapter_kwargs["task42_stage_gate"] is stage_gate
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(task038_launcher, "launch_specification", fake_launch)
    exit_code = run_case.main(
        [
            str(input_path),
            "--task42-packet-recovery-manifest",
            str(manifest_path),
            "--task42-packet-recovery-manifest-sha256",
            manifest_sha256,
        ]
    )
    capsys.readouterr()
    assert exit_code == 0
    assert captured["launch_manifest"] == manifest_path
    assert captured["launch_sha256"] == manifest_sha256
    assert captured["plan_manifest"] == manifest_path
    assert captured["plan_sha256"] == manifest_sha256


def _run_pre_recovery(
    monkeypatch,
    tmp_path,
    *,
    writer,
    progress=None,
    relative=1.0e-12,
    state=None,
):
    comm = _SerialCollective()
    factor = _Factor()
    if state is not None:
        state.append((factor, comm))
    monkeypatch.setattr(
        dtn, "_task42_strict_linear_residual", lambda *_args: _strict_residual(relative)
    )
    monkeypatch.setattr(
        dtn,
        "_task42_gather_auxiliary_values",
        lambda *_args: (np.asarray([1.0 + 0.0j]), None),
    )
    monkeypatch.setattr(dtn, "write_packet", writer)
    if progress is not None:
        monkeypatch.setattr(dtn, "_write_progress_event", progress)
    result = dtn._task42_pre_recovery_lifecycle(
        solve_A=object(),
        solve_b=_Vector([2.0]),
        solve_x=_Vector([1.0]),
        factor=factor,
        numeric_stage={"numeric_pass": True},
        n_fe=1,
        n_aux=1,
        modes=[],
        comm=comm,
        out_dir=tmp_path,
        started=None,
        petsc_options={},
        packet_directory=tmp_path / "packet",
        packet_identity={"task": "task42-test"},
    )
    return result, factor, comm


def test_task42_full_residual_consumer_uses_actual_full_helper_shape():
    measured = _residual()
    accepted = dtn._task42_full_residual_finite_status(measured)
    assert accepted["finite"] is True
    assert dtn._task42_full_residual_gate_pass(accepted) is True

    nan_value = dict(measured, eliminated_cell_interior_max_abs_residual=float("nan"))
    assert dtn._task42_full_residual_finite_status(nan_value)["finite"] is False

    missing = dict(measured)
    missing.pop("eliminated_cell_interior_residual_norm")
    assert dtn._task42_full_residual_finite_status(missing)["finite"] is False

    over_limit = dtn._task42_full_residual_finite_status(_residual(5.1e-9))
    assert over_limit["finite"] is True
    assert dtn._task42_full_residual_gate_pass(over_limit) is False


def test_task42_direct_summary_preserves_mat_solve_without_ksp_metadata(
    monkeypatch, tmp_path
):
    result, factor, _comm = _run_pre_recovery(
        monkeypatch,
        tmp_path,
        writer=lambda *_args, **_kwargs: {"pass": True},
        progress=lambda *_args, **_kwargs: None,
    )
    telemetry = result["solver_telemetry"]

    assert telemetry["solve_semantics"] == "direct_MatSolve_no_KSP_reason"
    assert "pc_factor_solver_type" not in telemetry
    assert (
        dtn._actual_pc_factor_solver_type(
            task42_staged_direct=True,
            external_snapshot=None,
            pre_recovery_solver_telemetry=telemetry,
            ksp=None,
        )
        is None
    )
    assert factor.destroy_calls == 1

    # Preserve the legacy KSP frozen-telemetry consumer contract separately;
    # this is not part of the Task42 direct MatSolve packet.
    legacy_ksp_telemetry = {"pc_factor_solver_type": "mumps"}
    assert (
        dtn._actual_pc_factor_solver_type(
            task42_staged_direct=False,
            external_snapshot=None,
            pre_recovery_solver_telemetry=legacy_ksp_telemetry,
            ksp=None,
        )
        == "mumps"
    )


def test_task42_infog17_inventory_rejects_unknown_or_malformed_schema():
    entry = {
        "index": 17,
        "api": "MatMumpsGetInfog",
        "label": "global_sum_symbolic_in_core_work_estimate",
        "raw_value": 321,
        "query_error_code": 0,
        "unit": "million_bytes_10^6_bytes; raw integer retained",
        "meaning_status": "verified_against_MUMPS_5.6.2_user_guide",
        "scope": (
            "MUMPS global field returned on this rank; do not sum replicated "
            "INFOG values across ranks"
        ),
    }
    assert dtn._task42_symbolic_memory_inventory(
        {"INFOG_api_raw_by_rank": [dict(entry, unit="bytes")]}
    ) is None
    assert dtn._task42_symbolic_memory_inventory(
        {
            "INFOG_api_raw_by_rank": [
                dict(entry, unit="million_bytes_10^6_bytes")
            ]
        }
    ) is None
    assert dtn._task42_symbolic_memory_inventory(
        {"INFOG_api_raw_by_rank": [dict(entry, raw_value=-1)]}
    ) is None
    assert dtn._task42_symbolic_memory_inventory({"INFOG_api_raw_by_rank": []}) is None


def test_task42_infog17_inventory_consumes_fresh_native_bridge_output():
    """Exercise the compiled C producer and the Task42 consumer together."""

    extension_value = os.environ.get("TASK42_LU_STAGE_BRIDGE_PATH")
    assert extension_value, "set TASK42_LU_STAGE_BRIDGE_PATH to the fresh build"
    extension_path = Path(extension_value).resolve(strict=True)
    repository_root = Path(__file__).resolve().parents[2]
    extension_path.relative_to(repository_root / "results")
    bridge = load_lu_stage_bridge(extension_path)

    comm = PETSc.COMM_WORLD
    mpi_comm = comm.tompi4py()
    owned: list[object] = []
    matrix = PETSc.Mat().createAIJ(size=(8, 8), nnz=3, comm=comm)
    owned.append(matrix)
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(5.0 + 0.25j))
        if row > 0:
            matrix.setValue(row, row - 1, PETSc.ScalarType(-0.5 + 0.2j))
        if row + 1 < 8:
            matrix.setValue(row, row + 1, PETSc.ScalarType(0.25 - 0.1j))
    matrix.assemblyBegin()
    matrix.assemblyEnd()

    factor = None
    try:
        factor = bridge.create_lu_stage(matrix, icntl14=None)
        factor.symbolic()
        analysis_info_raw = factor.analysis_info_raw()
        inventory = dtn._task42_symbolic_memory_inventory(analysis_info_raw)
        entries = analysis_info_raw.get("INFOG_api_raw_by_rank")
        assert isinstance(entries, list)
        infog17 = [
            row
            for row in entries
            if isinstance(row, dict)
            and row.get("index") == 17
            and row.get("api") == "MatMumpsGetInfog"
            and row.get("label") == "global_sum_symbolic_in_core_work_estimate"
        ]
        # All rank-local observations are gathered before assertions so a
        # malformed native result cannot strand another rank in a collective.
        observations = mpi_comm.allgather(
            {
                "infog17": infog17,
                "inventory": inventory,
                "stage": analysis_info_raw.get("stage"),
            }
        )
        print(
            "TASK42_NATIVE_INFOG17="
            + json.dumps(
                {
                    "rank": mpi_comm.rank,
                    "size": mpi_comm.size,
                    "entry": infog17[0] if len(infog17) == 1 else infog17,
                    "inventory": inventory,
                },
                sort_keys=True,
                allow_nan=False,
            ),
            flush=True,
        )
        assert len(infog17) == 1
        row = infog17[0]
        assert row["unit"] == "million_bytes_10^6_bytes; raw integer retained"
        assert row["query_error_code"] == 0
        assert type(row["raw_value"]) is int and row["raw_value"] >= 0
        assert row["meaning_status"] == "verified_against_MUMPS_5.6.2_user_guide"
        assert row["scope"] == (
            "MUMPS global field returned on this rank; do not sum replicated INFOG values across ranks"
        )
        assert inventory is not None
        assert inventory[0]["source_unit"] == row["unit"]
        assert inventory[0]["delta_bytes"] == row["raw_value"] * 1_000_000
        assert inventory[0]["scope"] == "global_replicated"
        assert inventory[0]["source_scope"].endswith(
            "count_once_not_summed_across_ranks"
        )
        assert all(item == observations[0] for item in observations)
        assert observations[0]["stage"] == "after_MatLUFactorSymbolic_before_numeric"

        # Keep an explicit-integer control beside the Task42 default-None
        # path. Both factors use this test's freshly compiled bridge artifact
        # and the same tiny PETSc matrix.
        cleanup = factor.destroy()
        factor = None
        assert cleanup.get("factor_released") is True
        assert cleanup.get("destroy_error_code") == 0

        explicit_factor = bridge.create_lu_stage(matrix, icntl14=40)
        try:
            explicit_factor.symbolic()
            explicit_lifecycle = explicit_factor.lifecycle()
            explicit_observations = mpi_comm.allgather(
                {
                    "requested": explicit_lifecycle.get("icntl14_requested"),
                    "actual": explicit_lifecycle.get("icntl14_actual"),
                    "error_code": explicit_lifecycle.get("icntl14_error_code"),
                    "readback": explicit_factor.get_mumps_icntl(14),
                    "symbolic_completed": explicit_lifecycle.get(
                        "symbolic_completed"
                    ),
                }
            )
            print(
                "TASK42_EXPLICIT_ICNTL14_CONTROL="
                + json.dumps(
                    {
                        "rank": mpi_comm.rank,
                        "size": mpi_comm.size,
                        "control": explicit_observations[mpi_comm.rank],
                    },
                    sort_keys=True,
                    allow_nan=False,
                ),
                flush=True,
            )
            assert all(item == explicit_observations[0] for item in explicit_observations)
            assert explicit_observations[0] == {
                "requested": 40,
                "actual": 40,
                "error_code": 0,
                "readback": 40,
                "symbolic_completed": True,
            }
        finally:
            explicit_cleanup = explicit_factor.destroy()
            assert explicit_cleanup.get("factor_released") is True
            assert explicit_cleanup.get("destroy_error_code") == 0

    finally:
        if factor is not None:
            cleanup = factor.destroy()
            assert cleanup.get("factor_released") is True
            assert cleanup.get("destroy_error_code") == 0
        for obj in reversed(owned):
            obj.destroy()


@pytest.mark.parametrize(
    "writer_mode",
    ["mock_refusal", "real_packet", "single_rank_local_error"],
)
def test_task42_staged_factory_same_factor_solve_packet_refusal_cleanup(
    monkeypatch, tmp_path, writer_mode
):
    """Exercise one factor through solve, packet handling, and destroy."""

    extension_value = os.environ.get("TASK42_LU_STAGE_BRIDGE_PATH")
    assert extension_value, "set TASK42_LU_STAGE_BRIDGE_PATH to the fresh build"
    extension_path = Path(extension_value).resolve(strict=True)
    repository_root = Path(__file__).resolve().parents[2]
    extension_path.relative_to(repository_root / "results")
    bridge = load_lu_stage_bridge(extension_path)
    comm = PETSc.COMM_WORLD
    mpi_comm = comm.tompi4py()

    matrix = PETSc.Mat().createAIJ(size=(8, 8), nnz=3, comm=comm)
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(5.0 + 0.25j))
        if row > 0:
            matrix.setValue(row, row - 1, PETSc.ScalarType(-0.5 + 0.2j))
        if row + 1 < 8:
            matrix.setValue(row, row + 1, PETSc.ScalarType(0.25 - 0.1j))
    matrix.assemblyBegin()
    matrix.assemblyEnd()

    gate_calls = {"symbolic": [], "numeric": [], "events": [], "solve": []}

    def pre_symbolic(context):
        gate_calls["symbolic"].append(context)
        return True

    def pre_numeric(context):
        analysis = context.get("analysis_info_raw")
        inventory = (
            dtn._task42_symbolic_memory_inventory(analysis)
            if isinstance(analysis, dict)
            else None
        )
        gate_calls["numeric"].append(
            {
                "icntl14_actual": context.get("icntl14_actual"),
                "analysis_inventory": inventory,
            }
        )
        return inventory is not None and type(context.get("icntl14_actual")) is int

    def stage_event(name, context):
        gate_calls["events"].append((name, context))

    factory = StagedMumpsLUFactory(
        bridge,
        pre_symbolic_gate=pre_symbolic,
        pre_numeric_gate=pre_numeric,
        stage_event_callback=stage_event,
        deferred_numeric_stage_identities=(TASK42_STAGED_DIRECT_STAGE_IDENTITY,),
    )
    factor = None
    rhs = matrix.createVecLeft()
    solution = matrix.createVecRight()
    expected_solution = np.asarray(
        [0.5 + index + 0.125j * (index + 1) for index in range(8)],
        dtype=np.complex128,
    )
    rhs_first, rhs_last = map(int, rhs.getOwnershipRange())
    for row in range(rhs_first, rhs_last):
        value = PETSc.ScalarType(5.0 + 0.25j) * expected_solution[row]
        if row > 0:
            value += PETSc.ScalarType(-0.5 + 0.2j) * expected_solution[row - 1]
        if row + 1 < 8:
            value += PETSc.ScalarType(0.25 - 0.1j) * expected_solution[row + 1]
        rhs.setValue(row, value)
    rhs.assemble()
    solution.set(PETSc.ScalarType(0.0))

    packet_snapshots = []

    shared_root_value = (
        str(tmp_path / "shared_task42_packet_root")
        if mpi_comm.rank == 0
        else None
    )
    shared_root_value = mpi_comm.bcast(shared_root_value, root=0)
    shared_root = Path(shared_root_value)
    if mpi_comm.rank == 0:
        shared_root.mkdir()
    mpi_comm.barrier()
    packet_directory = shared_root / "pre_recovery"

    def refuse_local_writer(_directory, captured_x, captured_b, **kwargs):
        packet_snapshots.append(
            {
                "x": captured_x,
                "b": captured_b,
                "metadata": kwargs["metadata"],
                "identity": kwargs["identity"],
            }
        )
        return {
            "pass": False,
            "errors": ["mocked_packet_preflight_failed:OSError"],
        }

    if writer_mode == "mock_refusal":
        monkeypatch.setattr(dtn, "write_packet", refuse_local_writer)
    elif writer_mode == "single_rank_local_error":
        failed_rank = mpi_comm.size - 1
        original_open = Path.open
        failed_temporary = packet_directory / f".rank{failed_rank:04d}.npz.tmp"

        def fail_one_rank_packet_open(path, *args, **kwargs):
            if mpi_comm.rank == failed_rank and path == failed_temporary:
                raise PermissionError("fixture blocks one rank packet shard")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail_one_rank_packet_open)
    elif writer_mode != "real_packet":
        raise AssertionError(f"unknown fixture writer mode: {writer_mode}")
    try:
        factor = factory(
            matrix,
            icntl14=None,
            stage_identity=TASK42_STAGED_DIRECT_STAGE_IDENTITY,
            defer_numeric=True,
        )
        symbolic_lifecycle = dict(factor.lifecycle)
        assert factor.stage_state == "symbolic_live_pending_numeric"
        assert symbolic_lifecycle["symbolic_attempts"] == 1
        assert symbolic_lifecycle["numeric_attempts"] == 0
        assert symbolic_lifecycle["icntl14_requested"] is None
        assert factor.analysis_info_raw["icntl14_requested"] is None

        numeric_info = factor.complete_numeric()
        assert factor.numeric_ready is True
        assert numeric_info["numeric_attempts"] == 1
        assert numeric_info["numeric_completed"] is True
        assert gate_calls["numeric"][0]["analysis_inventory"][0]["source_unit"] == (
            "million_bytes_10^6_bytes; raw integer retained"
        )
        assert type(gate_calls["numeric"][0]["icntl14_actual"]) is int

        solve_factor_id = id(factor)
        gate_calls["solve"].append(solve_factor_id)
        factor.solve(rhs, solution)
        assert len(gate_calls["solve"]) == 1
        assert gate_calls["solve"][0] == id(factor)

        lifecycle_error = None
        lifecycle_result = None
        try:
            lifecycle_result = dtn._task42_pre_recovery_lifecycle(
                solve_A=matrix,
                solve_b=rhs,
                solve_x=solution,
                factor=factor,
                numeric_stage=numeric_info,
                n_fe=8,
                n_aux=0,
                modes=[],
                comm=mpi_comm,
                out_dir=shared_root,
                started=None,
                petsc_options={},
                packet_directory=packet_directory,
                packet_identity={
                    "model_id": "task42-native-small-direct-contract",
                    "stage_identity": TASK42_STAGED_DIRECT_STAGE_IDENTITY,
                },
            )
        except RuntimeError as exc:
            lifecycle_error = exc

        should_refuse = writer_mode != "real_packet"
        if should_refuse:
            assert lifecycle_result is None
            assert lifecycle_error is not None
            assert "pre-recovery packet writer refused" in str(lifecycle_error)
        else:
            assert lifecycle_error is None
            assert lifecycle_result is not None
            assert lifecycle_result["packet"]["pass"] is True

        lifecycle_errors = mpi_comm.allgather(
            None if lifecycle_error is None else str(lifecycle_error)
        )
        if should_refuse:
            assert all(isinstance(value, str) for value in lifecycle_errors)
            assert len(set(lifecycle_errors)) == 1
            if writer_mode == "mock_refusal":
                assert "mocked_packet_preflight_failed:OSError" in lifecycle_errors[0]
            elif writer_mode == "single_rank_local_error":
                failed_rank = mpi_comm.size - 1
                expected_error = (
                    f"rank_{failed_rank}_packet_preflight_failed:"
                    "PermissionError: fixture blocks one rank packet shard"
                )
                assert expected_error in lifecycle_errors[0]
                assert packet_snapshots == []
        else:
            assert lifecycle_errors == [None] * mpi_comm.size

        assert factor.destroyed is True
        destroyed_lifecycle = dict(factor.lifecycle)
        assert destroyed_lifecycle["symbolic_attempts"] == 1
        assert destroyed_lifecycle["numeric_attempts"] == 1
        assert destroyed_lifecycle["destroy_attempts"] == 1
        assert destroyed_lifecycle["factor_released"] is True
        assert factory.live_factor_inventory == []
        assert len(factory.factor_release_history) == 1
        if writer_mode == "mock_refusal":
            assert len(packet_snapshots) == 1
            snapshot = packet_snapshots[0]
            residual = snapshot["metadata"]["residual"]
            assert residual["finite"] is True
            assert residual["linear_system_relative_residual"] <= 5.0e-9
            assert snapshot["metadata"]["task42_direct_original_residual_pass"] is True
            frozen_x = snapshot["x"].tobytes()
            frozen_b = snapshot["b"].tobytes()
        elif writer_mode == "real_packet":
            assert lifecycle_result is not None
            packet_result = lifecycle_result["packet"]
            snapshot = load_packet(
                Path(packet_result["manifest"]),
                identity={
                    "model_id": "task42-native-small-direct-contract",
                    "stage_identity": TASK42_STAGED_DIRECT_STAGE_IDENTITY,
                },
                expected_manifest_sha256=packet_result["manifest_sha256"],
                comm=mpi_comm,
            )
            residual = snapshot["metadata"]["residual"]
            assert residual["finite"] is True
            assert residual["linear_system_relative_residual"] <= 5.0e-9
            assert snapshot["metadata"]["task42_direct_original_residual_pass"] is True
            assert snapshot["global_size"] == 8
            ownership = tuple(map(int, matrix.getOwnershipRange()))
            assert snapshot["ownership_range"] == ownership
            expected_local_solution = expected_solution[slice(*ownership)]
            solution_relative_error = float(
                np.linalg.norm(snapshot["solution"] - expected_local_solution)
                / max(float(np.linalg.norm(expected_local_solution)), 1.0)
            )
            assert solution_relative_error <= 5.0e-9
            rhs_before_destroy = np.asarray(rhs.getArray(readonly=True)).copy()
            assert np.array_equal(snapshot["rhs"], rhs_before_destroy)
            frozen_x = snapshot["solution"].tobytes()
            frozen_b = snapshot["rhs"].tobytes()
        else:
            assert packet_snapshots == []
            residual = {
                "linear_system_relative_residual": None,
            }
            frozen_x = b""
            frozen_b = b""
        solution.set(PETSc.ScalarType(19.0 + 3.0j))
        rhs.set(PETSc.ScalarType(-7.0 + 2.0j))
        if writer_mode == "mock_refusal":
            assert snapshot["x"].tobytes() == frozen_x
            assert snapshot["b"].tobytes() == frozen_b
        elif writer_mode == "real_packet":
            reloaded = load_packet(
                Path(lifecycle_result["packet"]["manifest"]),
                identity={
                    "model_id": "task42-native-small-direct-contract",
                    "stage_identity": TASK42_STAGED_DIRECT_STAGE_IDENTITY,
                },
                expected_manifest_sha256=lifecycle_result["packet"][
                    "manifest_sha256"
                ],
                comm=mpi_comm,
            )
            assert reloaded["solution"].tobytes() == frozen_x
            assert reloaded["rhs"].tobytes() == frozen_b

        rank_summary = {
            "rank": int(mpi_comm.rank),
            "writer_mode": writer_mode,
            "writer_refused": should_refuse,
            "factor_destroyed": factor.destroyed,
            "lifecycle": destroyed_lifecycle,
            "residual_relative": residual["linear_system_relative_residual"],
            "snapshot_x_sha256": hashlib.sha256(frozen_x).hexdigest(),
            "snapshot_b_sha256": hashlib.sha256(frozen_b).hexdigest(),
        }
        rank_summaries = mpi_comm.allgather(rank_summary)
        assert len(rank_summaries) == mpi_comm.size
        assert all(
            row["writer_mode"] == writer_mode and row["factor_destroyed"]
            for row in rank_summaries
        )
        assert all(row["lifecycle"]["symbolic_attempts"] == 1 for row in rank_summaries)
        assert all(row["lifecycle"]["numeric_attempts"] == 1 for row in rank_summaries)
        print(
            "TASK42_STAGED_DIRECT_LIFECYCLE="
            + json.dumps(rank_summary, sort_keys=True, allow_nan=False),
            flush=True,
        )
    finally:
        if factor is not None and not factor.destroyed:
            factor.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_task42_local_writer_refusal_allows_consistent_factor_cleanup(
    monkeypatch, tmp_path
):
    progress_calls = []
    state = []

    def progress(*args, **kwargs):
        progress_calls.append((args, kwargs))

    def refuse_writer(*args, **kwargs):
        return {"pass": False, "errors": ["rank_0_packet_preflight_failed:OSError"]}

    with pytest.raises(RuntimeError, match="pre-recovery packet writer refused"):
        _run_pre_recovery(
            monkeypatch,
            tmp_path,
            writer=refuse_writer,
            progress=progress,
            state=state,
        )
    # A normal synchronized refusal reaches destroy/cleanup, but emits no
    # success progress marker.
    assert progress_calls == []
    assert state[0][0].destroy_calls == 1


def test_task42_collective_writer_exception_propagates_without_recovery_collectives(
    monkeypatch, tmp_path
):
    comm = _SerialCollective()
    factor = _Factor()
    sentinel = RuntimeError("MPI writer collective failed")
    monkeypatch.setattr(dtn, "_task42_strict_linear_residual", lambda *_: _strict_residual())
    monkeypatch.setattr(
        dtn,
        "_task42_gather_auxiliary_values",
        lambda *_: (np.asarray([1.0 + 0.0j]), None),
    )
    collective_count_at_writer = []

    def raise_from_writer(*args, **kwargs):
        collective_count_at_writer.append(comm.collective_count)
        raise sentinel

    monkeypatch.setattr(dtn, "write_packet", raise_from_writer)
    with pytest.raises(RuntimeError) as caught:
        dtn._task42_pre_recovery_lifecycle(
            solve_A=object(),
            solve_b=_Vector([2.0]),
            solve_x=_Vector([1.0]),
            factor=factor,
            numeric_stage={"numeric_pass": True},
            n_fe=1,
            n_aux=1,
            modes=[],
            comm=comm,
            out_dir=tmp_path,
            started=None,
            petsc_options={},
            packet_directory=tmp_path / "packet",
            packet_identity={"task": "task42-test"},
        )
    assert caught.value is sentinel
    assert factor.destroy_calls == 0
    assert collective_count_at_writer == [comm.collective_count]
    assert not any(kind == "allgather" for kind, _ in comm.calls)


def test_task42_progress_collective_exception_is_not_caught_for_recovery(
    monkeypatch, tmp_path
):
    comm = _SerialCollective()
    factor = _Factor()
    sentinel = RuntimeError("MPI progress collective failed")
    monkeypatch.setattr(dtn, "_task42_strict_linear_residual", lambda *_: _strict_residual())
    monkeypatch.setattr(
        dtn,
        "_task42_gather_auxiliary_values",
        lambda *_: (np.asarray([1.0 + 0.0j]), None),
    )
    monkeypatch.setattr(dtn, "write_packet", lambda *args, **kwargs: {"pass": True})
    collective_count_at_progress = []

    def raise_from_progress(*args, **kwargs):
        collective_count_at_progress.append(comm.collective_count)
        raise sentinel

    monkeypatch.setattr(dtn, "_write_progress_event", raise_from_progress)
    with pytest.raises(RuntimeError) as caught:
        dtn._task42_pre_recovery_lifecycle(
            solve_A=object(),
            solve_b=_Vector([2.0]),
            solve_x=_Vector([1.0]),
            factor=factor,
            numeric_stage={"numeric_pass": True},
            n_fe=1,
            n_aux=1,
            modes=[],
            comm=comm,
            out_dir=tmp_path,
            started=None,
            petsc_options={},
            packet_directory=tmp_path / "packet",
            packet_identity={"task": "task42-test"},
        )
    assert caught.value is sentinel
    assert factor.destroy_calls == 1
    assert collective_count_at_progress == [comm.collective_count]
