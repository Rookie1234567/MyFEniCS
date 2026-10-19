"""Task42 contracts, including an explicitly reduced 3D output integration fixture."""

from __future__ import annotations

import ast
import csv
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import src.solvers.common_3d_case_flow as common_flow
import src.solvers.dtn_port_3d as dtn
import src.solvers.solve_maxwell_3d_stage_4b_block_grating as stage4b
from scripts import run_case
from src.io.execution_plan import WORKER_MODULE, build_execution_plan
from src.io.input_validation import (
    _build_3d_config,
    simulation_config_3d_from_normalized,
    task42_profile_errors,
)
from src.io.resolved_config import canonical_json_bytes
from src.io.run_specification import RunSpecification
from src.runners import task038_full3d_direct, task038_input_worker, task038_launcher
from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverRequest
from src.solvers.full3d_lifecycle_packet import load_packet, write_packet
from src.solvers.petsc_lu_stage import (
    TASK42_STAGED_DIRECT_STAGE_IDENTITY,
    StagedMumpsLUFactory,
    load_lu_stage_bridge,
)

TASK42_13P5 = (
    Path(__file__).resolve().parents[2]
    / "input/official/task42hybrid_az90_50x50_17x20_0p7nm"
    / "13p5nm_p6h10_full3d_direct_mpi8.dat"
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


def test_task42_packet_restore_reports_rebuilt_action_layout_before_vec_duplicate(
    tmp_path: Path,
) -> None:
    """Report the actual per-rank action/RHS ranges on a safe collective refusal."""

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("the deliberately uneven PETSc ownership fixture requires MPI2")
    case = _write_small_task42_recovery_packet(tmp_path, comm)
    operator = case["operator"]
    solution = case["solution"]
    packet_rhs = case["rhs"]
    uneven_rhs = PETSc.Vec().createMPI(
        (1 if comm.rank == 0 else 3, 4), comm=comm
    )
    tracked_rhs = _DuplicateTrackingVector(uneven_rhs)
    refcount_before = int(uneven_rhs.getRefCount())
    local_layout = {
        "rank": int(comm.rank),
        "matrix_size": [int(value) for value in operator.getSize()],
        "matrix_global_rows": int(operator.getSize()[0]),
        "matrix_ownership_range": [
            int(value) for value in operator.getOwnershipRange()
        ],
        "matrix_local_rows": int(
            operator.getOwnershipRange()[1] - operator.getOwnershipRange()[0]
        ),
        "rhs_global_size": int(uneven_rhs.getSize()),
        "rhs_local_size": int(uneven_rhs.getLocalSize()),
        "rhs_ownership_range": [
            int(value) for value in uneven_rhs.getOwnershipRange()
        ],
        "n_fe": int(case["n_fe"]),
        "n_aux": int(case["n_aux"]),
        "packet_global_size": 4,
        "packet_ownership_range": [
            int(value) for value in packet_rhs.getOwnershipRange()
        ],
        "packet_solution_shape": [
            int(solution.getLocalSize())
        ],
        "packet_rhs_shape": [int(packet_rhs.getLocalSize())],
    }
    layout_rows = comm.allgather(local_layout)
    try:
        request_modes = tuple(reversed(case["modes"]))
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
            modes=request_modes,
        )
        recovery_port = dtn.task42_packet_recovery_port(
            case["manifest_path"],
            manifest_sha256=case["manifest_sha256"],
            identity=case["identity"],
        )
        with pytest.raises(ValueError, match="Task42 packet restore rejected") as error:
            recovery_port(request)

        error_texts = comm.allgather(str(error.value))
        assert len(set(error_texts)) == 1
        error_text = error_texts[0]
        assert "archived vector layout does not match the rebuilt action" in error_text
        assert "external-key order differs" not in error_text
        diagnostics_text = error_text.split(
            "; layout_diagnostics_by_rank=", maxsplit=1
        )[1]
        diagnostics_by_rank = json.loads(diagnostics_text)
        assert len(diagnostics_by_rank) == comm.size
        expected_actual_modes = dtn._pre_recovery_mode_keys(list(request_modes))
        expected_archived_modes = dtn._pre_recovery_mode_keys(
            list(case["modes"])
        )
        for diagnostic in diagnostics_by_rank:
            assert diagnostic["schema"] == "task42.packet_recovery.layout_diagnostics.v1"
            observed = diagnostic["observed"]
            mode_order = observed["mode_order"]
            assert mode_order["source"] == "same_request.modes"
            assert mode_order["actual_request_modes"] == expected_actual_modes
            assert mode_order["actual_request_modes_count"] == case["n_aux"]
            assert mode_order["actual_order_matches_archived_packet"] is False
            assert len(mode_order["actual_request_modes_sha256"]) == 64
            assert mode_order["archived_packet_external_keys"] == expected_archived_modes
            trace_map = observed["trace_map"]
            assert trace_map["available"] is True
            assert trace_map["entry_count"] == 2
            assert trace_map["original_index_range"] == [0, 1]
            assert trace_map["active_index_range"] == [0, 1]
            assert len(trace_map["original_to_active_sha256"]) == 64
        for row in layout_rows:
            assert f'"rank":{row["rank"]}' in error_text
            for field in (
                "matrix_size",
                "matrix_global_rows",
                "matrix_local_rows",
                "matrix_ownership_range",
                "rhs_global_size",
                "rhs_local_size",
                "rhs_ownership_range",
                "n_fe",
                "n_aux",
                "packet_global_size",
                "packet_ownership_range",
                "packet_solution_shape",
                "packet_rhs_shape",
            ):
                expected = json.dumps(row[field], separators=(",", ":"))
                assert f'"{field}":{expected}' in error_text
        expected_checks = {
            "matrix_is_square_2d": True,
            "matrix_global_size_matches_packet": True,
            "matrix_global_size_matches_n_fe_plus_n_aux": True,
            "matrix_and_rhs_ownership_ranges_match": False,
            "rhs_global_size_matches_matrix": True,
            "packet_ownership_range_matches_rhs": False,
            "packet_solution_rhs_are_matching_vectors": True,
            "packet_local_size_matches_rhs_range": False,
        }
        for name, passed in expected_checks.items():
            assert f'"{name}":{str(passed).lower()}' in error_text
        assert tracked_rhs.duplicate_calls == 0
        print(
            json.dumps(
                {
                    "case": "uneven_action_layout_collective_refusal",
                    "collective_failure_vector": error_text,
                },
                sort_keys=True,
            )
        )

        refcount_after = int(uneven_rhs.getRefCount())
        refcount_rows = comm.allgather(
            {"rank": int(comm.rank), "before": refcount_before, "after": refcount_after}
        )
        assert all(row["before"] == row["after"] for row in refcount_rows)
        assert tuple(uneven_rhs.getOwnershipRange()) == (
            (0, 1) if comm.rank == 0 else (1, 4)
        )
        assert tuple(operator.getOwnershipRange()) == (
            (0, 2) if comm.rank == 0 else (2, 4)
        )
    finally:
        uneven_rhs.destroy()
        packet_rhs.destroy()
        solution.destroy()
        operator.destroy()
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
        layout_diagnostics = snapshot.recovery_evidence["layout_diagnostics"]
        assert layout_diagnostics["pass"] is True
        assert all(layout_diagnostics["checks"].values())
        mode_order = layout_diagnostics["observed"]["mode_order"]
        assert mode_order["source"] == "same_request.modes"
        assert mode_order["actual_request_modes"] == dtn._pre_recovery_mode_keys(
            list(case["modes"])
        )
        assert mode_order["actual_order_matches_archived_packet"] is True
        assert len(mode_order["actual_request_modes_sha256"]) == 64
        trace_map = layout_diagnostics["observed"]["trace_map"]
        assert trace_map["available"] is True
        assert trace_map["entry_count"] == 2
        assert trace_map["original_index_range"] == [0, 1]
        assert trace_map["active_index_range"] == [0, 1]
        assert trace_map["original_to_active_sha256"] == snapshot.recovery_evidence[
            "rebuilt_trace_map_sha256"
        ]
        assert layout_diagnostics["observed"]["rhs_ownership_range"] == list(
            rhs.getOwnershipRange()
        )
        assert layout_diagnostics["observed"]["packet_ownership_range"] == list(
            rhs.getOwnershipRange()
        )
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


_TASK42_RECOVERY_BINDING_KEYS = {
    "task42_packet_recovery_manifest",
    "task42_packet_recovery_manifest_sha256",
    "task42_packet_recovery_identity",
}


def _call_named(source: str, function_name: str) -> ast.Call:
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == function_name
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == function_name
        )
    ]
    assert len(matches) == 1, (
        f"expected one call to {function_name}, got {len(matches)}"
    )
    return matches[0]


def _bind_static_call(call: ast.Call, target) -> set[str]:
    assert not any(isinstance(argument, ast.Starred) for argument in call.args)
    assert all(keyword.arg is not None for keyword in call.keywords)
    keyword_values = {keyword.arg: object() for keyword in call.keywords}
    inspect.signature(target).bind(
        *([object()] * len(call.args)),
        **keyword_values,
    )
    return set(keyword_values)


def test_task42_packet_recovery_callsite_keywords_bind_all_public_layers() -> None:
    call_layers = (
        (
            inspect.getsource(task038_full3d_direct._run_solver),
            "run_stage4b_block_grating_3d_case",
            stage4b.run_stage4b_block_grating_3d_case,
        ),
        (
            inspect.getsource(stage4b.run_stage4b_block_grating_3d_case),
            "run_prepared_3d_case_flow",
            common_flow.run_prepared_3d_case_flow,
        ),
        (
            inspect.getsource(common_flow.run_prepared_3d_case_flow),
            "solve_stage4_dtn_port_total_field",
            dtn.solve_stage4_dtn_port_total_field,
        ),
    )
    for source, callee_name, callee in call_layers:
        forwarded = _bind_static_call(_call_named(source, callee_name), callee)
        assert _TASK42_RECOVERY_BINDING_KEYS <= forwarded
    assert _TASK42_RECOVERY_BINDING_KEYS <= set(
        inspect.signature(dtn._solve_stage4_dtn_port_total_field_impl).parameters
    )


class _CleanupProbe:
    def __init__(self):
        self.destroy_calls = 0

    def destroy(self):
        self.destroy_calls += 1


def _call_public_dtn_recovery_wrapper(**overrides):
    bindings = {
        "task42_packet_recovery_manifest": Path("/archive/manifest.json"),
        "task42_packet_recovery_manifest_sha256": "a" * 64,
        "task42_packet_recovery_identity": {"run_id": "task42-test"},
    }
    bindings.update(overrides)
    return dtn.solve_stage4_dtn_port_total_field(
        a=None,
        L=None,
        V=None,
        mesh_data=None,
        cfg=None,
        floquet_data=None,
        petsc_options={},
        out_dir=Path("/tmp/task42-dtn-wrapper-test"),
        log=lambda *_args: None,
        linear_solver_port=object(),
        task42_stage_gate=lambda *_args: {"pass": True},
        matrix_free_dtn=True,
        **bindings,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"task42_packet_recovery_manifest_sha256": None},
        {"task42_packet_recovery_identity": None},
        {"task42_packet_recovery_manifest": None},
    ],
    ids=("missing-sha", "missing-identity", "missing-manifest"),
)
def test_public_dtn_wrapper_rejects_partial_task42_recovery_binding(
    monkeypatch, overrides
) -> None:
    def implementation(**_kwargs):
        pytest.fail("invalid recovery bindings must be rejected before _impl")

    monkeypatch.setattr(
        dtn, "_solve_stage4_dtn_port_total_field_impl", implementation
    )
    with pytest.raises(ValueError, match="binding validation failed"):
        _call_public_dtn_recovery_wrapper(**overrides)


@pytest.mark.parametrize(
    "fail_in_impl", [False, True], ids=("return", "primary-error")
)
def test_public_dtn_wrapper_forwards_archive_binding_and_preserves_cleanup(
    monkeypatch, fail_in_impl: bool
) -> None:
    cleanup_probe = _CleanupProbe()
    captured = {}
    result = {"recovery": "forwarded"}

    def implementation(**kwargs):
        captured.update(kwargs)
        kwargs["_recovery_cleanup_sink"].append(cleanup_probe)
        assert kwargs["task42_packet_recovery_manifest"] == Path(
            "/archive/manifest.json"
        )
        assert kwargs["task42_packet_recovery_manifest_sha256"] == "a" * 64
        assert kwargs["task42_packet_recovery_identity"] == {
            "run_id": "task42-test"
        }
        if fail_in_impl:
            raise RuntimeError("primary implementation error")
        return result

    monkeypatch.setattr(
        dtn, "_solve_stage4_dtn_port_total_field_impl", implementation
    )
    if fail_in_impl:
        with pytest.raises(RuntimeError, match="primary implementation error"):
            _call_public_dtn_recovery_wrapper()
    else:
        assert _call_public_dtn_recovery_wrapper() is result
    assert cleanup_probe.destroy_calls == 1
    assert captured["_recovery_cleanup_sink"] == [cleanup_probe]


def test_mpi_public_dtn_wrapper_recovery_binding_mismatch_is_collective(
    monkeypatch,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size < 2:
        pytest.skip("requires the authorized MPI2 invocation")
    implementation_calls = []

    def implementation(**_kwargs):
        implementation_calls.append(comm.rank)
        pytest.fail("mismatched per-rank bindings must be rejected before _impl")

    monkeypatch.setattr(
        dtn, "_solve_stage4_dtn_port_total_field_impl", implementation
    )
    identity = {"run_id": "task42-test", "rank_marker": comm.rank}
    with pytest.raises(ValueError, match="bindings must match on every MPI rank"):
        _call_public_dtn_recovery_wrapper(task42_packet_recovery_identity=identity)
    assert implementation_calls == []


def test_mpi_public_dtn_wrapper_accepts_identical_recovery_binding(
    monkeypatch,
) -> None:
    comm = MPI.COMM_WORLD
    implementation_calls = []
    result = {"rank": comm.rank}

    def implementation(**kwargs):
        implementation_calls.append(comm.rank)
        assert kwargs["task42_packet_recovery_manifest_sha256"] == "a" * 64
        assert kwargs["task42_packet_recovery_identity"] == {
            "run_id": "task42-test"
        }
        return result

    monkeypatch.setattr(dtn, "_solve_stage4_dtn_port_total_field_impl", implementation)
    assert _call_public_dtn_recovery_wrapper() is result
    assert implementation_calls == [comm.rank]


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


def _task42_small_full_output_specification(
    artifact_root: Path,
) -> RunSpecification:
    """Keep Task42 physics fixed in a p2/h50/MPI1 fixture, not a formal A1 run."""

    from src.io import load_and_resolve

    official = load_and_resolve(TASK42_13P5)
    fixture_input = TASK42_13P5.read_text(encoding="utf-8")
    replacements = (
        (
            'run_id = "task42_13p5_p6h10_full3d_direct_mpi8"',
            'run_id = "task42_13p5_test_only_p2h50_direct_recovery"',
        ),
        ("nedelec_degree = 6", "nedelec_degree = 2"),
        ("visualization_degree = 6", "visualization_degree = 2"),
        ("mesh_target_nm = 10.0", "mesh_target_nm = 50.0"),
        ("mpi_size = 8", "mpi_size = 1"),
    )
    for old, new in replacements:
        if fixture_input.count(old) != 1:
            raise AssertionError(f"test-only Task42 input field is not unique: {old}")
        fixture_input = fixture_input.replace(old, new, 1)
    fixture_input = (
        "# TEST-ONLY reduced-discretization fixture; not a formal Task42 A1 run.\n"
        + fixture_input
    )
    fixture_bytes = fixture_input.encode("utf-8")
    fixture_input_path = artifact_root / "task42_test_only_p2h50_mpi1.dat"
    fixture_input_path.write_bytes(fixture_bytes)

    normalized = official.as_jsonable()
    identity = dict(official.identity)
    identity["run_id"] = "task42_13p5_test_only_p2h50_direct_recovery"
    normalized["run_id"] = identity["run_id"]
    discretization = dict(official.discretization)
    discretization.update(
        {
            "nedelec_degree": 2,
            "visualization_degree": 2,
            "mesh_target_nm": 50.0,
        }
    )
    execution = dict(official.execution)
    execution["mpi_size"] = 1
    normalized["discretization"] = discretization
    normalized["execution"] = execution
    normalized["derived"] = _build_3d_config(normalized)
    physical = {
        section: normalized[section]
        for section in (
            "geometry",
            "materials",
            "incidence",
            "discretization",
            "boundary",
        )
    }
    physical_sha256 = hashlib.sha256(canonical_json_bytes(physical)).hexdigest()
    input_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    output_parent = (
        Path(str(official.output["results_root"]))
        / str(official.identity["model_id"])
        / f"{identity['run_id']}__full3d_direct__mpi1__Mna"
    )
    specification = replace(
        official,
        identity=identity,
        discretization=discretization,
        execution=execution,
        derived=normalized["derived"],
        source_path=fixture_input_path,
        raw_input_bytes=fixture_bytes,
        input_sha256=input_sha256,
        physical_model_sha256=physical_sha256,
        expected_output_parent=output_parent,
    )
    payload = specification.as_jsonable()
    official_payload = official.as_jsonable()
    assert official_payload["output"]["top_probe_z_nm"] == pytest.approx(125.0)
    assert official_payload["output"]["bottom_probe_z_nm"] == pytest.approx(-5.0)
    assert official_payload["output"]["reference_plane_z_nm"] == [
        10.0,
        30.0,
        60.0,
        90.0,
        110.0,
    ]
    for section in ("geometry", "materials", "incidence", "boundary", "method", "solver"):
        assert payload[section] == official_payload[section]
    return specification


def test_task42_diffraction_probes_use_uniform_exterior_layers() -> None:
    from src.io import load_and_resolve
    from src.postprocessing.diffraction_3d import _probe_z_locations

    payload = load_and_resolve(TASK42_13P5).as_jsonable()
    cfg = simulation_config_3d_from_normalized(payload)
    assert task42_profile_errors(payload) == []
    assert _probe_z_locations(cfg) == pytest.approx((125.0, -5.0))
    invalid_top_payload = dict(payload)
    invalid_top_payload["output"] = dict(payload["output"])
    invalid_top_payload["output"]["top_probe_z_nm"] = 110.0
    assert any(
        path == "output.top_probe_z_nm"
        for path, _message in task42_profile_errors(invalid_top_payload)
    )
    invalid_bottom_payload = dict(payload)
    invalid_bottom_payload["output"] = dict(payload["output"])
    invalid_bottom_payload["output"]["bottom_probe_z_nm"] = 10.0
    assert any(
        path == "output.bottom_probe_z_nm"
        for path, _message in task42_profile_errors(invalid_bottom_payload)
    )
    with pytest.raises(ValueError, match="above the block top z=120 nm"):
        _probe_z_locations(replace(cfg, diffraction_top_probe_z=110.0))
    with pytest.raises(ValueError, match="uniform substrate layer"):
        _probe_z_locations(replace(cfg, diffraction_bottom_probe_z=10.0))


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="reduced Task42 direct-to-packet-recovery output fixture is serial",
)
def test_task42_small_direct_packet_recovery_writes_full_physical_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    """Run actual Task42 direct and recovery paths on a test-only reduced 3D mesh."""

    assert os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") == "1"
    for thread_name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        assert os.environ.get(thread_name) == "1", thread_name

    configured_root = os.environ.get("TASK42_TINY_OUTPUT_ROOT")
    artifact_root = (
        Path(configured_root).resolve()
        if configured_root
        else (tmp_path / "task42_small_direct_recovery").resolve()
    )
    artifact_root.mkdir(parents=True, exist_ok=False)
    specification = _task42_small_full_output_specification(artifact_root)
    payload = specification.as_jsonable()
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
    ).strip()
    source_files = (
        "input/official/task42hybrid_az90_50x50_17x20_0p7nm/13p5nm_p6h10_full3d_direct_mpi8.dat",
        "src/io/input_validation.py",
        "src/postprocessing/diffraction_3d.py",
        "src/runners/task038_full3d_direct.py",
        "src/runners/task038_input_worker.py",
        "src/runners/task038_launcher.py",
        "src/solvers/dtn_port_3d.py",
        "src/solvers/full3d_lifecycle_packet.py",
        "src/test/test_task42_direct_contract.py",
    )
    source_file_hashes = {
        name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
        for name in source_files
    }
    source_sha = hashlib.sha1(
        json.dumps(
            {"git_head": git_head, "source_files_sha256": source_file_hashes},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert len(source_sha) == 40
    bridge_path = Path(
        os.environ[task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV]
    ).resolve(strict=True)
    assert bridge_path.is_file()
    bridge_build_record_path = bridge_path.parents[1] / "build_commands.json"
    bridge_build_record = json.loads(
        bridge_build_record_path.read_text(encoding="utf-8")
    )
    bridge_source_path = Path(bridge_build_record["source_path"]).resolve(strict=True)
    bridge_sha256 = hashlib.sha256(bridge_path.read_bytes()).hexdigest()
    bridge_source_sha256 = hashlib.sha256(bridge_source_path.read_bytes()).hexdigest()
    assert bridge_build_record["extension_sha256"] == bridge_sha256
    assert bridge_build_record["source_sha256"] == bridge_source_sha256
    adapter_identity = task038_launcher.method_adapter_identity(
        "full3d_direct", str(payload["model_id"])
    )
    captured_results: list[dict[str, Any]] = []
    original_adapter = task038_full3d_direct.run_full3d_direct

    def capture_actual_adapter_result(*args, **kwargs):
        result = original_adapter(*args, **kwargs)
        captured_results.append(result)
        return result

    monkeypatch.setattr(
        task038_full3d_direct,
        "run_full3d_direct",
        capture_actual_adapter_result,
    )
    monkeypatch.setenv("TASK038_JOB_ROOT_PID", str(os.getpid()))

    def run_worker_attempt(
        label: str,
        *,
        recovery_manifest: Path | None = None,
        recovery_manifest_sha256: str | None = None,
    ) -> tuple[dict[str, Any], Path, str]:
        run_root = (artifact_root / label).resolve()
        run_root.mkdir()
        _manifest, resolved_sha256 = task038_launcher._write_bootstrap(
            specification,
            run_root,
            source_sha=source_sha,
            adapter_identity=adapter_identity,
            start_time=datetime.now(timezone.utc).isoformat(),
        )
        if recovery_manifest is None:
            monkeypatch.setenv(
                task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV,
                str(bridge_path),
            )
        else:
            monkeypatch.delenv(
                task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV,
                raising=False,
            )
        result_count_before = len(captured_results)
        dispatch_status = task038_input_worker._dispatch_resolved_payload(
            payload,
            expected_method="full3d_direct",
            output_directory=run_root,
            expected_source_sha=source_sha,
            expected_resolved_config_sha256=resolved_sha256,
            task42_packet_recovery_manifest=recovery_manifest,
            task42_packet_recovery_manifest_sha256=recovery_manifest_sha256,
            comm=MPI.COMM_WORLD,
        )
        dispatch_receipt = run_root / "worker_dispatch_result.json"
        dispatch_receipt.write_text(
            json.dumps(
                {
                    "schema": "task42.test_worker_dispatch_result.v1",
                    "run_label": label,
                    "status_code": int(dispatch_status[0]),
                    "errors": list(dispatch_status[1]),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        assert dispatch_status == (0, [])
        assert len(captured_results) == result_count_before + 1
        adapter_result = captured_results[-1]
        assert adapter_result["passed"] is True, adapter_result.get("errors")
        run_manifest = json.loads(
            (run_root / "run_manifest.json").read_text(encoding="utf-8")
        )
        resolved_path = run_root / "resolved_config.json"
        input_path = run_root / "input_original.dat"
        assert hashlib.sha256(resolved_path.read_bytes()).hexdigest() == resolved_sha256
        assert hashlib.sha256(input_path.read_bytes()).hexdigest() == specification.input_sha256
        assert run_manifest["source_sha"] == source_sha
        assert run_manifest["resolved_config_sha256"] == resolved_sha256
        assert run_manifest["output_directory"] == str(run_root)
        assert run_manifest["numerical_output_directory"] == str(
            run_root / "numerical_output"
        )
        return adapter_result, run_root / "numerical_output", resolved_sha256

    direct_result, direct_output, direct_resolved_sha256 = run_worker_attempt(
        "direct"
    )
    direct_summary = direct_result["summary"]
    assert isinstance(direct_summary, dict)
    assert direct_summary["actual_pc_factor_solver_type"] == "MATSOLVERMUMPS"
    packet_manifest = direct_output / "pre_recovery_packet" / "manifest.json"
    assert packet_manifest.is_file()
    packet_manifest_sha256 = hashlib.sha256(packet_manifest.read_bytes()).hexdigest()
    packet = json.loads(packet_manifest.read_text(encoding="utf-8"))
    assert packet["identity"]["source_sha"] == source_sha
    assert packet["identity"]["input_sha256"] == specification.input_sha256
    assert packet["identity"]["physical_model_sha256"] == specification.physical_model_sha256
    assert packet["identity"]["resolved_config_sha256"] == direct_resolved_sha256
    assert packet["metadata"]["task42_direct_original_residual_pass"] is True

    recovery_result, recovery_output, recovery_resolved_sha256 = run_worker_attempt(
        "recovery",
        recovery_manifest=packet_manifest,
        recovery_manifest_sha256=packet_manifest_sha256,
    )
    recovery_summary = recovery_result["summary"]
    assert isinstance(recovery_summary, dict)
    assert recovery_resolved_sha256 == direct_resolved_sha256
    assert recovery_summary["task42_packet_recovery"] is not None
    recovery_evidence = recovery_summary["task42_packet_recovery_evidence"]
    assert recovery_evidence["global_factor_called"] is False
    assert recovery_evidence["new_physical_solve_called"] is False
    assert recovery_summary["actual_pc_factor_solver_type"] is None

    output_receipts: dict[str, dict[str, Any]] = {}
    loaded_fields: dict[str, dict[str, np.ndarray]] = {}
    for label, output, summary in (
        ("direct", direct_output, direct_summary),
        ("recovery", recovery_output, recovery_summary),
    ):
        full_residual = summary["task42_full_true_residual"]
        assert full_residual["finite"] is True
        relative_residual = float(summary["linear_system_relative_residual"])
        assert np.isfinite(relative_residual) and 0.0 <= relative_residual <= 5.0e-9
        assert full_residual["linear_system_relative_residual"] == relative_residual
        assert summary["case_status"] == "completed"
        assert summary["official_result"] is True
        assert summary["external_rta_gate_pass"] is True
        for key in (
            "R_total",
            "T_total",
            "A_balance",
            "A_volume_total",
            "energy_closure_error_port_volume",
        ):
            assert np.isfinite(float(summary[key])), (label, key, summary.get(key))

        field_path = Path(summary["paraview_file"])
        if not field_path.is_absolute():
            field_path = output / field_path
        assert field_path.is_file(), (label, field_path)
        import pyvista as pv

        grid = pv.read(field_path)
        arrays: dict[str, np.ndarray] = {}
        for field_name in ("E_tot_V_per_m", "H_A_per_m"):
            for suffix in ("real", "imag", "abs"):
                key = f"{field_name}_{suffix}"
                values = np.asarray(grid.point_data[key])
                assert values.size > 0 and np.isfinite(values).all(), (label, key)
                if suffix == "abs":
                    assert float(np.max(values)) > 0.0, (label, key)
                if suffix != "abs":
                    arrays[key] = values.copy()
        loaded_fields[label] = arrays

        port_path = output / "port_power.json"
        diffraction_path = output / "dtn_port_diffraction_orders_3d.json"
        volume_path = output / "volume_absorption.json"
        summary_csv = output / "power_summary.csv"
        for required_path in (port_path, diffraction_path, volume_path, summary_csv):
            assert required_path.is_file(), (label, required_path)
        port_data = json.loads(port_path.read_text(encoding="utf-8"))
        diffraction_data = json.loads(diffraction_path.read_text(encoding="utf-8"))
        volume_data = json.loads(volume_path.read_text(encoding="utf-8"))
        orders = diffraction_data["orders"]
        assert orders and {row["side"] for row in orders} == {"top", "bottom"}
        assert all(abs(int(row["m"])) <= 3 and abs(int(row["n"])) <= 7 for row in orders)
        expected_order_keys = {
            (
                str(row["side"]),
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]),
            )
            for row in payload["derived"]["external_mode_inventory"]["keys"]
        }
        reported_order_keys = {
            (
                str(row["side"]),
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]),
            )
            for row in orders
        }
        assert reported_order_keys == expected_order_keys
        assert port_data["R_total"] == pytest.approx(summary["R_total"], abs=1.0e-12)
        assert port_data["T_total"] == pytest.approx(summary["T_total"], abs=1.0e-12)
        assert volume_data["A_volume_total"] == pytest.approx(
            summary["A_volume_total"], abs=1.0e-12
        )
        assert float(summary["R_total"]) + float(summary["T_total"]) + float(
            summary["A_volume_total"]
        ) - 1.0 == pytest.approx(
            float(summary["energy_closure_error_port_volume"]), abs=1.0e-10
        )
        with summary_csv.open(newline="", encoding="utf-8") as stream:
            power_rows = list(csv.DictReader(stream))
        assert power_rows and {"R", "T", "A", "status", "source"}.issubset(
            power_rows[0]
        )
        output_receipts[label] = {
            "run_root": str(output.parent),
            "relative_residual": relative_residual,
            "R_total": float(summary["R_total"]),
            "T_total": float(summary["T_total"]),
            "A_balance": float(summary["A_balance"]),
            "A_volume_total": float(summary["A_volume_total"]),
            "energy_closure_error_port_volume": float(
                summary["energy_closure_error_port_volume"]
            ),
            "port_power_sha256": hashlib.sha256(port_path.read_bytes()).hexdigest(),
            "diffraction_sha256": hashlib.sha256(
                diffraction_path.read_bytes()
            ).hexdigest(),
            "volume_absorption_sha256": hashlib.sha256(
                volume_path.read_bytes()
            ).hexdigest(),
            "field_sha256": hashlib.sha256(field_path.read_bytes()).hexdigest(),
            "field_path": str(field_path),
            "reported_diffraction_order_count": len(orders),
        }

    assert direct_summary["linear_system_relative_residual"] == pytest.approx(
        recovery_summary["linear_system_relative_residual"], abs=1.0e-10
    )
    for key in ("R_total", "T_total", "A_balance", "A_volume_total"):
        assert direct_summary[key] == pytest.approx(recovery_summary[key], abs=1.0e-8)
    for field_name in loaded_fields["direct"]:
        np.testing.assert_allclose(
            loaded_fields["direct"][field_name],
            loaded_fields["recovery"][field_name],
            rtol=1.0e-8,
            atol=1.0e-12,
        )

    packet_sha256 = hashlib.sha256(packet_manifest.read_bytes()).hexdigest()
    receipt = {
        "schema": "task42.small_direct_packet_recovery_output_test.v1",
        "classification": "test_fixture_only_not_formal_A1",
        "source_sha": source_sha,
        "git_head": git_head,
        "source_identity_type": "test-only fingerprint of HEAD plus listed working source hashes",
        "source_files_sha256": source_file_hashes,
        "official_input_sha256": hashlib.sha256(TASK42_13P5.read_bytes()).hexdigest(),
        "test_input_sha256": specification.input_sha256,
        "test_physical_model_sha256": specification.physical_model_sha256,
        "bridge_path": str(bridge_path),
        "bridge_sha256": bridge_sha256,
        "bridge_source_path": str(bridge_source_path),
        "bridge_source_sha256": bridge_source_sha256,
        "physics_unchanged_from_official": True,
        "test_discretization": dict(specification.discretization),
        "test_mpi_size": int(specification.execution["mpi_size"]),
        "packet_manifest_sha256": packet_sha256,
        "packet_source_sha256": packet["identity"]["source_sha"],
        "direct": output_receipts["direct"],
        "recovery": output_receipts["recovery"],
        "evidence_boundary": (
            "actual reduced-mesh Task42 material/geometry/incidence through worker adapter, "
            "direct factor/solve, packet write, packet restore, full residual and field/RTA output; "
            "not the registered p6/h10/MPI8 public launch profile or formal A1 qualification"
        ),
    }
    (artifact_root / "test_result.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="saved Task42 direct packet in this attempt is serial",
)
def test_task42_saved_packet_recovery_writes_outputs_without_new_factor(
    tmp_path: Path, monkeypatch
) -> None:
    """Recover the saved tiny solve; do not create another factor or solution."""

    assert os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") == "1"
    for thread_name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        assert os.environ.get(thread_name) == "1", thread_name

    saved_direct_text = os.environ.get("TASK42_SAVED_DIRECT_OUTPUT")
    if not saved_direct_text:
        pytest.skip("no explicitly bound saved Task42 direct output was supplied")
    saved_direct = Path(saved_direct_text).resolve(strict=True)
    saved_numerical = saved_direct / "numerical_output"
    original_manifest_path = saved_direct / "run_manifest.json"
    original_resolved_path = saved_direct / "resolved_config.json"
    original_input_path = saved_direct / "input_original.dat"
    packet_manifest = saved_numerical / "pre_recovery_packet" / "manifest.json"
    for required in (
        original_manifest_path,
        original_resolved_path,
        original_input_path,
        packet_manifest,
    ):
        assert required.is_file(), required

    original_manifest_bytes = original_manifest_path.read_bytes()
    original_resolved_bytes = original_resolved_path.read_bytes()
    original_input_bytes = original_input_path.read_bytes()
    packet_manifest_bytes = packet_manifest.read_bytes()
    original_manifest = json.loads(original_manifest_bytes)
    archive_payload = json.loads(original_resolved_bytes)
    packet = json.loads(packet_manifest_bytes)
    archive_manifest_sha256 = hashlib.sha256(packet_manifest_bytes).hexdigest()
    archive_resolved_sha256 = hashlib.sha256(original_resolved_bytes).hexdigest()
    archive_input_sha256 = hashlib.sha256(original_input_bytes).hexdigest()
    archive_source_sha = str(original_manifest["source_sha"])
    archive_physical_sha256 = str(original_manifest["physical_model_sha256"])
    assert archive_manifest_sha256 == (
        "cbc5d4f742e9ba46b91d53e38a56add0573000d9504cfc32a00468724d981a25"
    )
    assert hashlib.sha256(original_resolved_bytes).hexdigest() == (
        original_manifest["resolved_config_sha256"]
    )
    assert archive_input_sha256 == original_manifest["input_sha256"]
    assert archive_input_sha256 == archive_payload["provenance"]["input_sha256"]
    assert archive_physical_sha256 == archive_payload["provenance"]["physical_model_sha256"]
    assert archive_source_sha == packet["identity"]["source_sha"]
    assert archive_resolved_sha256 == packet["identity"]["resolved_config_sha256"]
    assert archive_payload["output"]["top_probe_z_nm"] == pytest.approx(110.0)
    assert archive_payload["output"]["bottom_probe_z_nm"] == pytest.approx(10.0)
    assert archive_payload["geometry"]["grating_height_nm"] == pytest.approx(120.0)
    assert archive_payload["execution"]["mpi_size"] == 1

    direct_progress = saved_numerical / "progress_3d.jsonl"
    progress_rows = [
        json.loads(line)
        for line in direct_progress.read_text(encoding="utf-8").splitlines()
    ]
    direct_residual_rows = [
        row for row in progress_rows if row.get("stage") == "after_true_residual"
    ]
    assert len(direct_residual_rows) == 1
    direct_relative_residual = float(
        direct_residual_rows[0]["linear_system_relative_residual"]
    )
    assert np.isfinite(direct_relative_residual)
    assert direct_relative_residual <= 5.0e-9
    direct_vtu = saved_numerical / "fields_3d_for_paraview.vtu"
    assert direct_vtu.is_file()
    direct_bp_paths = (
        saved_numerical / "E_3d_numerical.bp",
        saved_numerical / "H_3d_A_per_m_from_curl.bp",
    )
    for bp_path in direct_bp_paths:
        assert (bp_path / "data.0").is_file() and (bp_path / "data.0").stat().st_size > 0
    import pyvista as pv

    prior_direct_grid = pv.read(direct_vtu)
    for field_name in ("E_tot_V_per_m", "H_A_per_m"):
        magnitude = np.asarray(prior_direct_grid.point_data[f"{field_name}_abs"])
        assert magnitude.size and np.isfinite(magnitude).all()
        assert float(magnitude.max()) > 0.0

    configured_root = os.environ.get("TASK42_TINY_OUTPUT_ROOT")
    output_root = (
        Path(configured_root).resolve()
        if configured_root
        else (tmp_path / "task42_saved_packet_recovery").resolve()
    )
    output_root.mkdir(parents=True, exist_ok=False)
    run_root = output_root / "recovery"
    run_root.mkdir()
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
    ).strip()
    payload = json.loads(json.dumps(archive_payload))
    payload["output"]["top_probe_z_nm"] = 125.0
    payload["output"]["bottom_probe_z_nm"] = -5.0
    assert task038_full3d_direct._task42_output_only_delta_errors(
        archive_payload, payload, allow_probe_override=True
    ) == []
    bad_geometry_payload = json.loads(json.dumps(payload))
    bad_geometry_payload["geometry"]["grating_height_nm"] += 1.0
    assert task038_full3d_direct._task42_output_only_delta_errors(
        archive_payload, bad_geometry_payload, allow_probe_override=True
    )
    bad_output_payload = json.loads(json.dumps(payload))
    bad_output_payload["output"]["diffraction_order_max_m"] += 1
    assert task038_full3d_direct._task42_output_only_delta_errors(
        archive_payload, bad_output_payload, allow_probe_override=True
    )
    effective_resolved_bytes = canonical_json_bytes(payload) + b"\n"
    effective_resolved_sha256 = hashlib.sha256(effective_resolved_bytes).hexdigest()
    resolved_path = run_root / "resolved_config.json"
    input_copy_path = run_root / "input_original.dat"
    manifest_path = run_root / "run_manifest.json"
    resolved_path.write_bytes(effective_resolved_bytes)
    input_copy_path.write_bytes(original_input_bytes)
    recovery_manifest = dict(original_manifest)
    recovery_manifest.update(
        {
            "output_directory": str(run_root),
            "numerical_output_directory": str(run_root / "numerical_output"),
            "status": "recovery_only_running",
            "result_classification": "not_run",
            "exit_status": None,
            "source_sha": git_head,
            "resolved_config_sha256": effective_resolved_sha256,
            "task42_current_source_sha_kind": "launcher_git_rev_parse_HEAD",
            "task42_packet_recovery_archive_source_sha": archive_source_sha,
            "task42_packet_recovery_archive_resolved_config_sha256": (
                archive_resolved_sha256
            ),
            "task42_packet_recovery_source_manifest_sha256": hashlib.sha256(
                original_manifest_bytes
            ).hexdigest(),
        }
    )
    manifest_path.write_text(
        json.dumps(recovery_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_root / "source_sha.txt").write_text(git_head + "\n", encoding="ascii")
    (run_root / "input_sha256.txt").write_text(
        archive_input_sha256 + "\n", encoding="ascii"
    )
    (run_root / "physical_model_sha256.txt").write_text(
        archive_physical_sha256 + "\n", encoding="ascii"
    )

    method_adapter = task038_launcher.method_adapter_identity(
        "full3d_direct", str(payload["model_id"])
    )
    worker_errors = task038_input_worker.validate_worker_contract(
        resolved_config=resolved_path,
        manifest=manifest_path,
        expected_input_sha256=archive_input_sha256,
        expected_physical_model_sha256=archive_physical_sha256,
        expected_source_sha=git_head,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=method_adapter,
        expected_output_directory=run_root,
        expected_resolved_config_sha256=effective_resolved_sha256,
        actual_mpi_size=MPI.COMM_WORLD.size,
    )
    assert worker_errors == []
    assert recovery_manifest["source_sha"] != archive_source_sha
    assert recovery_manifest["task42_packet_recovery_archive_source_sha"] == (
        archive_source_sha
    )

    from src.postprocessing.diffraction_3d import _probe_z_locations

    old_cfg = simulation_config_3d_from_normalized(archive_payload)
    with pytest.raises(ValueError, match="above the block top z=120 nm"):
        _probe_z_locations(old_cfg)
    reduced_test_profile_error_paths = [
        "run_id",
        "discretization.nedelec_degree",
        "discretization.visualization_degree",
        "discretization.mesh_target_nm",
        "execution.mpi_size",
    ]
    archive_profile_error_paths = [
        path for path, _message in task42_profile_errors(archive_payload)
    ]
    effective_profile_error_paths = [
        path for path, _message in task42_profile_errors(payload)
    ]
    assert archive_profile_error_paths == [
        *reduced_test_profile_error_paths,
        "output.top_probe_z_nm",
        "output.bottom_probe_z_nm",
    ]
    assert effective_profile_error_paths == reduced_test_profile_error_paths
    # This packet is from the explicitly reduced p2/h50/MPI1 integration fixture;
    # it is not a pass of the official p6/h10/MPI8 Task42 input profile. The actual
    # recovery worker contract is validated below without changing archived physics.
    assert _probe_z_locations(simulation_config_3d_from_normalized(payload)) == pytest.approx(
        (125.0, -5.0)
    )
    effective_output_bytes = canonical_json_bytes(payload) + b"\n"
    effective_output_path = run_root / "numerical_output" / "effective_output_config.json"
    output_identity_path = (
        run_root / "numerical_output" / "output_sampling_identity.json"
    )
    output_override = {"top_probe_z_nm": 125.0, "bottom_probe_z_nm": -5.0}
    output_override_receipt = {
        "schema": "task42.packet_recovery_output_probe_override.v1",
        "policy": "postprocess_only_after_original_archive_identity_pass",
        "archive_config_path": str(saved_direct / "resolved_config.json"),
        "archive_source_sha": archive_source_sha,
        "archive_input_sha256": archive_input_sha256,
        "archive_resolved_config_sha256": archive_resolved_sha256,
        "archive_physical_model_sha256": archive_physical_sha256,
        "archive_probe_values_nm": {
            "top_probe_z_nm": 110.0,
            "bottom_probe_z_nm": 10.0,
        },
        "effective_probe_values_nm": output_override,
        "effective_output_config_path": str(effective_output_path),
        "effective_output_config_sha256": hashlib.sha256(
            effective_output_bytes
        ).hexdigest(),
        "effective_run_resolved_config_path": str(resolved_path),
        "effective_run_resolved_config_sha256": effective_resolved_sha256,
        "output_sampling_identity_path": str(output_identity_path),
        "physical_discretization_and_mode_identity_unchanged": True,
    }

    monkeypatch.setenv("TASK038_JOB_ROOT_PID", str(os.getpid()))
    monkeypatch.delenv(
        task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV,
        raising=False,
    )
    wrong_archive_source_status = task038_input_worker._dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=run_root,
        expected_source_sha=git_head,
        expected_resolved_config_sha256=effective_resolved_sha256,
        task42_packet_recovery_manifest=packet_manifest,
        task42_packet_recovery_manifest_sha256=archive_manifest_sha256,
        task42_packet_recovery_archive_source_sha="0" * 40,
        task42_packet_recovery_archive_resolved_config_sha256=archive_resolved_sha256,
        task42_packet_recovery_output_probes=output_override,
        comm=MPI.COMM_WORLD,
    )
    (run_root / "wrong_archive_source_dispatch_result.json").write_text(
        json.dumps(
            {
                "schema": "task42.saved_packet_recovery_wrong_source.v1",
                "status_code": int(wrong_archive_source_status[0]),
                "errors": list(wrong_archive_source_status[1]),
                "full_error_vector_persisted_before_assertion": True,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert wrong_archive_source_status[0] == 4
    assert wrong_archive_source_status[1]
    assert not (run_root / "numerical_output").exists()

    invalid_probe_status = task038_input_worker._dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=run_root,
        expected_source_sha=git_head,
        expected_resolved_config_sha256=effective_resolved_sha256,
        task42_packet_recovery_manifest=packet_manifest,
        task42_packet_recovery_manifest_sha256=archive_manifest_sha256,
        task42_packet_recovery_archive_source_sha=archive_source_sha,
        task42_packet_recovery_archive_resolved_config_sha256=archive_resolved_sha256,
        task42_packet_recovery_output_probes={
            "top_probe_z_nm": 110.0,
            "bottom_probe_z_nm": 10.0,
        },
        comm=MPI.COMM_WORLD,
    )
    invalid_probe_receipt = {
        "schema": "task42.saved_packet_recovery_invalid_override.v1",
        "status_code": int(invalid_probe_status[0]),
        "errors": list(invalid_probe_status[1]),
        "full_error_vector_persisted_before_assertion": True,
    }
    (run_root / "invalid_probe_worker_dispatch_result.json").write_text(
        json.dumps(invalid_probe_receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    assert invalid_probe_status[0] == 4
    assert any(
        "must match the effective resolved config" in error
        for error in invalid_probe_status[1]
    ), invalid_probe_status
    assert not (run_root / "numerical_output").exists()

    captured_adapter_results: list[dict[str, Any]] = []
    original_adapter = task038_full3d_direct.run_full3d_direct

    def capture_recovery_result(*args, **kwargs):
        result = original_adapter(*args, **kwargs)
        captured_adapter_results.append(result)
        return result

    monkeypatch.setattr(
        task038_full3d_direct,
        "run_full3d_direct",
        capture_recovery_result,
    )
    dispatch_status = task038_input_worker._dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=run_root,
        expected_source_sha=git_head,
        expected_resolved_config_sha256=effective_resolved_sha256,
        task42_packet_recovery_manifest=packet_manifest,
        task42_packet_recovery_manifest_sha256=archive_manifest_sha256,
        task42_packet_recovery_archive_source_sha=archive_source_sha,
        task42_packet_recovery_archive_resolved_config_sha256=archive_resolved_sha256,
        task42_packet_recovery_output_probes=output_override,
        comm=MPI.COMM_WORLD,
    )
    dispatch_receipt = {
        "schema": "task42.saved_packet_recovery_dispatch.v1",
        "status_code": int(dispatch_status[0]),
        "errors": list(dispatch_status[1]),
        "full_error_vector_persisted_before_assertion": True,
        "archive_manifest_sha256": archive_manifest_sha256,
        "archive_resolved_config_sha256": archive_resolved_sha256,
        "effective_run_resolved_config_sha256": effective_resolved_sha256,
        "effective_output_config_sha256": hashlib.sha256(
            effective_output_bytes
        ).hexdigest(),
    }
    (run_root / "worker_dispatch_result.json").write_text(
        json.dumps(dispatch_receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    assert dispatch_status == (0, []), dispatch_status
    assert len(captured_adapter_results) == 1
    adapter_result = captured_adapter_results[0]
    adapter_summary = adapter_result.get("summary")
    adapter_probe_receipt = (
        adapter_summary.get("task42_packet_recovery_output_probe_override")
        if isinstance(adapter_summary, dict)
        else None
    )
    (run_root / "adapter_result.json").write_text(
        json.dumps(
            {
                "passed": bool(adapter_result.get("passed")),
                "errors": list(adapter_result.get("errors", [])),
                "numerical_output_directory": adapter_result.get(
                    "numerical_output_directory"
                ),
                "task42_packet_recovery_output_probe_override": adapter_probe_receipt,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert adapter_result["passed"] is True, adapter_result.get("errors")
    recovered_summary = adapter_result["summary"]
    assert isinstance(recovered_summary, dict)

    recovered_summary_path = run_root / "numerical_output" / "run_summary.json"
    recovery_result_path = run_root / "adapter_result.json"
    assert recovered_summary_path.is_file()
    persisted_summary = json.loads(recovered_summary_path.read_text(encoding="utf-8"))
    assert persisted_summary["case_status"] == "completed"
    assert persisted_summary["linear_system_relative_residual"] == pytest.approx(
        recovered_summary["linear_system_relative_residual"]
    )
    assert recovered_summary["case_status"] == "completed"
    assert recovered_summary["official_result"] is True
    assert recovered_summary["external_rta_gate_pass"] is True
    recovery = recovered_summary["task42_packet_recovery_evidence"]
    assert recovery["global_factor_called"] is False
    assert recovery["new_physical_solve_called"] is False
    assert recovered_summary["actual_pc_factor_solver_type"] is None
    assert recovered_summary["task42_packet_recovery_output_probe_override"] == {
        **output_override_receipt,
        "output_sampling_identity_sha256": hashlib.sha256(
            canonical_json_bytes(output_override_receipt) + b"\n"
        ).hexdigest(),
    }
    actual_effective_bytes = effective_output_path.read_bytes()
    assert actual_effective_bytes == effective_output_bytes
    actual_effective_payload = json.loads(actual_effective_bytes)
    for key, value in payload.items():
        if key != "output":
            assert actual_effective_payload[key] == value, key
    for key, value in payload["output"].items():
        if key not in {"top_probe_z_nm", "bottom_probe_z_nm"}:
            assert actual_effective_payload["output"][key] == value, key
    assert json.loads(output_identity_path.read_text(encoding="utf-8")) == (
        output_override_receipt
    )
    full_residual = recovered_summary["task42_full_true_residual"]
    relative_residual = float(recovered_summary["linear_system_relative_residual"])
    assert full_residual["finite"] is True
    assert np.isfinite(relative_residual) and relative_residual <= 5.0e-9
    assert full_residual["linear_system_relative_residual"] == relative_residual

    output_root_numerical = run_root / "numerical_output"
    field_path = Path(recovered_summary["paraview_file"])
    if not field_path.is_absolute():
        field_path = output_root_numerical / field_path
    recovered_grid = pv.read(field_path)
    for field_name in ("E_tot_V_per_m", "H_A_per_m"):
        for suffix in ("real", "imag", "abs"):
            values = np.asarray(recovered_grid.point_data[f"{field_name}_{suffix}"])
            assert values.size and np.isfinite(values).all()
            if suffix == "abs":
                assert float(values.max()) > 0.0

    port_path = output_root_numerical / "port_power.json"
    diffraction_path = output_root_numerical / "diffraction_orders_3d.json"
    dtn_port_diffraction_path = (
        output_root_numerical / "dtn_port_diffraction_orders_3d.json"
    )
    volume_path = output_root_numerical / "volume_absorption.json"
    reference_json = output_root_numerical / "full3d_reference_samples.json"
    reference_npz = output_root_numerical / "full3d_reference_samples.npz"
    for path in (
        port_path,
        diffraction_path,
        dtn_port_diffraction_path,
        volume_path,
        reference_json,
        reference_npz,
        field_path,
    ):
        assert path.is_file() and path.stat().st_size > 0, path
    port_data = json.loads(port_path.read_text(encoding="utf-8"))
    diffraction_data = json.loads(diffraction_path.read_text(encoding="utf-8"))
    dtn_port_diffraction_data = json.loads(
        dtn_port_diffraction_path.read_text(encoding="utf-8")
    )
    volume_data = json.loads(volume_path.read_text(encoding="utf-8"))
    diffraction_metrics = diffraction_data["metrics"]
    assert diffraction_metrics["diffraction_top_probe_z"] == pytest.approx(125.0)
    assert diffraction_metrics["diffraction_bottom_probe_z"] == pytest.approx(-5.0)
    assert diffraction_metrics["diffraction_order_count"] > 0
    assert dtn_port_diffraction_data["metrics"][
        "diffraction_total_power_source"
    ] == "dtn_port_modal_amplitudes"
    assert dtn_port_diffraction_data["orders"]
    assert port_data["R_total"] == pytest.approx(recovered_summary["R_total"])
    assert port_data["T_total"] == pytest.approx(recovered_summary["T_total"])
    assert volume_data["A_volume_total"] == pytest.approx(
        recovered_summary["A_volume_total"]
    )
    for key in (
        "R_total",
        "T_total",
        "A_balance",
        "A_volume_total",
        "energy_closure_error_port_volume",
    ):
        assert np.isfinite(float(recovered_summary[key])), key
    assert set(json.loads(reference_json.read_text(encoding="utf-8"))) >= {
        "schema_version",
        "archive_sha256",
        "components",
    }
    with np.load(reference_npz, allow_pickle=False) as reference_arrays:
        assert reference_arrays.files
        assert all(
            np.isfinite(np.asarray(reference_arrays[name])).all()
            for name in reference_arrays.files
        )

    output_hashes = {
        str(path.relative_to(run_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            recovered_summary_path,
            effective_output_path,
            output_identity_path,
            port_path,
            diffraction_path,
            dtn_port_diffraction_path,
            volume_path,
            reference_json,
            reference_npz,
            field_path,
            recovery_result_path,
        )
    }
    final_receipt = {
        "schema": "task42.saved_packet_recovery_full_output_test.v1",
        "classification": "test_fixture_only_not_formal_A1",
        "source_identity": {
            "git_head": git_head,
            "current_worker_source_sha": git_head,
            "current_worker_source_sha_kind": "launcher_git_rev_parse_HEAD;working_tree_file_hashes_listed_separately",
            "archive_source_sha": archive_source_sha,
            "archive_source_sha_kind": (
                "historical test-only SHA-1 fingerprint over git HEAD plus the then-current SHA-256 values of three source files; "
                "not a Git commit and historical component hashes were not persisted independently"
            ),
            "current_source_files_sha256": {
                path: hashlib.sha256(
                    (Path(__file__).resolve().parents[2] / path).read_bytes()
                ).hexdigest()
                for path in (
                    "input/official/task42hybrid_az90_50x50_17x20_0p7nm/13p5nm_p6h10_full3d_direct_mpi8.dat",
                    "src/io/input_validation.py",
                    "src/postprocessing/diffraction_3d.py",
                    "src/runners/task038_launcher.py",
                    "src/runners/task038_full3d_direct.py",
                    "src/runners/task038_input_worker.py",
                    "src/solvers/full3d_lifecycle_packet.py",
                    "src/test/test_task42_direct_contract.py",
                )
            },
        },
        "archive": {
            "attempt_output": str(saved_direct),
            "manifest_sha256": archive_manifest_sha256,
            "resolved_config_sha256": archive_resolved_sha256,
            "input_sha256": archive_input_sha256,
            "physical_model_sha256": archive_physical_sha256,
            "source_sha": archive_source_sha,
            "prior_direct_guard_reproduction": (
                "Top diffraction probe z=110 nm must be above the block top z=120 nm."
            ),
            "prior_direct_relative_residual": direct_relative_residual,
            "prior_direct_dispatch_error_vector": "not_persisted_exactly; pytest stdout retained truncated assertion repr",
        },
        "output_identity": output_override_receipt,
        "recovery": {
            "relative_residual": relative_residual,
            "R_total": float(recovered_summary["R_total"]),
            "T_total": float(recovered_summary["T_total"]),
            "A_balance": float(recovered_summary["A_balance"]),
            "A_volume_total": float(recovered_summary["A_volume_total"]),
            "energy_closure_error_port_volume": float(
                recovered_summary["energy_closure_error_port_volume"]
            ),
            "factors_created": False,
            "physical_solve_called": False,
            "output_sha256": output_hashes,
        },
    }
    recovery_result_path.write_text(
        json.dumps(final_receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def test_task42_output_probe_receipts_are_root_written_and_collectively_bound(
    tmp_path: Path, monkeypatch
) -> None:
    """Only rank 0 writes recovery receipts; all ranks get the same outcome."""

    comm = MPI.COMM_WORLD
    assert os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") == "1"
    for thread_name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        assert os.environ.get(thread_name) == "1", thread_name

    saved_direct_text = os.environ.get("TASK42_SAVED_DIRECT_OUTPUT")
    if not saved_direct_text:
        pytest.skip("no explicitly bound saved Task42 archive was supplied")
    saved_direct = Path(saved_direct_text).resolve(strict=True)
    archive_run_manifest = json.loads(
        (saved_direct / "run_manifest.json").read_text(encoding="utf-8")
    )
    archive_config_path = saved_direct / "resolved_config.json"
    archive_config_bytes = archive_config_path.read_bytes()
    archive_payload = json.loads(archive_config_bytes)
    packet_manifest = (
        saved_direct / "numerical_output" / "pre_recovery_packet" / "manifest.json"
    )
    packet_manifest_bytes = packet_manifest.read_bytes()
    archive_manifest_sha256 = hashlib.sha256(packet_manifest_bytes).hexdigest()
    archive_resolved_sha256 = hashlib.sha256(archive_config_bytes).hexdigest()
    archive_source_sha = str(archive_run_manifest["source_sha"])
    assert archive_source_sha == "8b90d0147d11fe34e604dbf4474820c7d7748a24"
    assert archive_manifest_sha256 == (
        "cbc5d4f742e9ba46b91d53e38a56add0573000d9504cfc32a00468724d981a25"
    )
    assert archive_resolved_sha256 == (
        "db1d5a43fc7be4b61ff906ea3f3a5d8a8c20916bc0ec677577cde1dc774cf986"
    )

    payload = json.loads(json.dumps(archive_payload))
    payload["output"]["top_probe_z_nm"] = 125.0
    payload["output"]["bottom_probe_z_nm"] = -5.0
    effective_resolved_sha256 = hashlib.sha256(
        canonical_json_bytes(payload) + b"\n"
    ).hexdigest()
    repository_root = Path(__file__).resolve().parents[2]
    current_source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()
    shared_root = Path(comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0))
    evidence_root_text = os.environ.get("TASK42_TINY_OUTPUT_ROOT")
    if not evidence_root_text:
        pytest.skip("no attempt-bound Task42 evidence directory was supplied")
    evidence_root = Path(evidence_root_text).resolve()
    if comm.rank == 0:
        evidence_root.mkdir(parents=True, exist_ok=False)
    comm.Barrier()
    monkeypatch.setenv("TASK038_JOB_ROOT_PID", str(os.getpid()))
    monkeypatch.delenv(
        task038_input_worker.TASK42_STAGED_DIRECT_BRIDGE_PATH_ENV,
        raising=False,
    )

    observations: dict[str, list[dict[str, Any]]] = {}

    def run_case(
        case_name: str,
        *,
        expected_probe_values: dict[str, float] | None = None,
        source_override: str | None = None,
        preexisting_effective: bool = False,
        fail_identity_write: bool = False,
    ) -> list[dict[str, Any]]:
        run_directory = shared_root / case_name
        numerical_output = run_directory / "numerical_output"
        effective_path = numerical_output / "effective_output_config.json"
        identity_path = numerical_output / "output_sampling_identity.json"
        sentinel = b"preexisting effective config must not be overwritten\n"
        if comm.rank == 0:
            run_directory.mkdir(parents=True, exist_ok=False)
            if preexisting_effective:
                numerical_output.mkdir()
                effective_path.write_bytes(sentinel)
        comm.Barrier()

        open_attempts: list[str] = []
        solver_calls = 0
        real_path_open = Path.open

        def tracked_path_open(path, *args, **kwargs):
            if path in {effective_path, identity_path}:
                open_attempts.append(path.name)
                if (
                    fail_identity_write
                    and comm.rank == 0
                    and path == identity_path
                ):
                    raise OSError("injected root-only output identity write failure")
            return real_path_open(path, *args, **kwargs)

        def fake_solver_runner(_cfg, _numerical_output, **_kwargs):
            nonlocal solver_calls
            solver_calls += 1
            from benchmarks.canonical_vector_artifacts import MANIFEST_SCHEMA

            canonical_roles = None
            if comm.rank == 0:
                canonical_root = run_directory / "test_canonical_export"
                canonical_root.mkdir()
                canonical_roles = {}
                for role_name in ("active_trace", "full_fe"):
                    manifest_path = canonical_root / f"{role_name}.json"
                    manifest_bytes = (
                        json.dumps(
                            {
                                "schema_version": MANIFEST_SCHEMA,
                                "fixture_only": True,
                                "role": role_name,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    manifest_path.write_bytes(manifest_bytes)
                    canonical_roles[role_name] = {
                        "schema_version": MANIFEST_SCHEMA,
                        "manifest": str(manifest_path),
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        "global_summed_packet_count": 1,
                    }
            canonical_roles = comm.bcast(canonical_roles, root=0)
            return {
                "case_status": "completed",
                "official_result": True,
                "linear_system_relative_residual": 1.0e-13,
                "R_total": 0.5,
                "T_total": 0.4,
                "A_volume_total": 0.1,
                "full3d_direct_canonical_export": {
                    "roles": canonical_roles,
                    "test_fixture_only": True,
                },
            }

        caught_error = None
        result = None
        with monkeypatch.context() as context:
            context.setattr(Path, "open", tracked_path_open)
            try:
                result = task038_full3d_direct.run_full3d_direct(
                    payload,
                    run_directory,
                    solver_runner=fake_solver_runner,
                    source_sha=current_source_sha,
                    resolved_config_sha256=effective_resolved_sha256,
                    task42_stage_gate=lambda *_args, **_kwargs: None,
                    task42_bridge_path=None,
                    task42_packet_recovery_manifest=packet_manifest,
                    task42_packet_recovery_manifest_sha256=archive_manifest_sha256,
                    task42_packet_recovery_archive_source_sha=(
                        source_override or archive_source_sha
                    ),
                    task42_packet_recovery_archive_resolved_config_sha256=(
                        archive_resolved_sha256
                    ),
                    task42_packet_recovery_output_probes=(
                        expected_probe_values
                        if expected_probe_values is not None
                        else {"top_probe_z_nm": 125.0, "bottom_probe_z_nm": -5.0}
                    ),
                )
            except ValueError as exc:
                caught_error = f"{type(exc).__name__}: {exc}"

        receipt = None
        summary = None
        adapter_errors = []
        if result is not None:
            summary = result.get("summary")
            if isinstance(summary, Mapping):
                receipt = summary.get("task42_packet_recovery_output_probe_override")
            adapter_errors = list(result.get("errors", []))
        expected_classification = {
            "success": "accepted",
            "preexisting_effective": "preexisting_file_refusal",
            "identity_write_failure": "root_writer_refusal",
            "wrong_archive_source": "archive_identity_refusal",
            "invalid_probe": "probe_contract_refusal",
        }[case_name]
        actual_classification = (
            "raised_refusal"
            if caught_error is not None
            else "accepted"
            if result is not None and bool(result.get("passed"))
            else "adapter_rejected"
            if result is not None
            else "no_result"
        )
        local_observation = {
            "rank": int(comm.rank),
            "error": caught_error,
            "passed": None if result is None else bool(result.get("passed")),
            "adapter_errors": adapter_errors,
            "summary": summary,
            "expected_classification": expected_classification,
            "actual_classification": actual_classification,
            "solver_calls": solver_calls,
            "writer_open_attempts": open_attempts,
            "receipt": receipt,
            "effective_exists": effective_path.is_file(),
            "effective_sha256": (
                hashlib.sha256(effective_path.read_bytes()).hexdigest()
                if effective_path.is_file()
                else None
            ),
            "identity_exists": identity_path.is_file(),
        }
        case_observations = comm.allgather(local_observation)
        observations[case_name] = case_observations
        if comm.rank == 0:
            (evidence_root / "output_probe_writer_contract.json").write_text(
                json.dumps(
                    {
                        "schema": "task42.output_probe_writer_mpi_contract.v1",
                        "archive_source_sha": archive_source_sha,
                        "archive_manifest_sha256": archive_manifest_sha256,
                        "archive_resolved_config_sha256": archive_resolved_sha256,
                        "current_git_head": current_source_sha,
                        "current_source_files_sha256": {
                            path: hashlib.sha256(
                                (repository_root / path).read_bytes()
                            ).hexdigest()
                            for path in (
                                "src/runners/task038_full3d_direct.py",
                                "src/test/test_task42_direct_contract.py",
                            )
                        },
                        "cases": observations,
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        comm.Barrier()
        return case_observations

    success = run_case("success")
    preexisting = run_case("preexisting_effective", preexisting_effective=True)
    write_failure = run_case("identity_write_failure", fail_identity_write=True)
    wrong_source = run_case("wrong_archive_source", source_override="0" * 40)
    invalid_probe = run_case(
        "invalid_probe",
        expected_probe_values={"top_probe_z_nm": 110.0, "bottom_probe_z_nm": 10.0},
    )

    assert all(row["error"] is None and row["passed"] is True for row in success), success
    assert all(row["adapter_errors"] == [] for row in success), success
    assert all(row["actual_classification"] == "accepted" for row in success), success
    assert all(
        row["expected_classification"] == "accepted" for row in success
    ), success
    assert all(isinstance(row["summary"], Mapping) for row in success), success
    assert all(row["solver_calls"] == 1 for row in success)
    assert [row["writer_open_attempts"] for row in success] == [
        ["effective_output_config.json", "output_sampling_identity.json"],
        *([[]] * (comm.size - 1)),
    ]
    success_receipts = [row["receipt"] for row in success]
    assert all(receipt == success_receipts[0] for receipt in success_receipts)
    success_receipt = success_receipts[0]
    assert isinstance(success_receipt, Mapping)
    success_effective = shared_root / "success" / "numerical_output" / "effective_output_config.json"
    success_identity = shared_root / "success" / "numerical_output" / "output_sampling_identity.json"
    effective_bytes = success_effective.read_bytes()
    identity_bytes = success_identity.read_bytes()
    assert hashlib.sha256(effective_bytes).hexdigest() == success_receipt[
        "effective_output_config_sha256"
    ]
    assert hashlib.sha256(identity_bytes).hexdigest() == success_receipt[
        "output_sampling_identity_sha256"
    ]
    identity_payload = json.loads(identity_bytes)
    assert identity_payload == {
        key: value
        for key, value in success_receipt.items()
        if key != "output_sampling_identity_sha256"
    }

    for observations_for_case, expected_attempts, expected_identity in (
        (preexisting, ["effective_output_config.json"], False),
        (
            write_failure,
            ["effective_output_config.json", "output_sampling_identity.json"],
            False,
        ),
    ):
        errors = [row["error"] for row in observations_for_case]
        assert all(isinstance(error, str) for error in errors)
        assert len(set(errors)) == 1
        assert all(row["actual_classification"] == "raised_refusal" for row in observations_for_case)
        assert all(row["passed"] is None and row["solver_calls"] == 0 for row in observations_for_case)
        assert [row["writer_open_attempts"] for row in observations_for_case] == [
            expected_attempts,
            *([[]] * (comm.size - 1)),
        ]
        assert all(row["identity_exists"] is expected_identity for row in observations_for_case)
    preexisting_path = (
        shared_root / "preexisting_effective" / "numerical_output" / "effective_output_config.json"
    )
    assert preexisting_path.read_bytes() == b"preexisting effective config must not be overwritten\n"
    assert all(row["error"] is not None for row in wrong_source)
    assert len({row["error"] for row in wrong_source}) == 1
    assert all(
        row["actual_classification"] == "raised_refusal" for row in wrong_source
    )
    assert all(row["solver_calls"] == 0 for row in wrong_source)
    assert all(row["writer_open_attempts"] == [] for row in wrong_source)
    assert all(row["error"] is not None for row in invalid_probe)
    assert len({row["error"] for row in invalid_probe}) == 1
    assert all(
        row["actual_classification"] == "raised_refusal" for row in invalid_probe
    )
    assert all(row["solver_calls"] == 0 for row in invalid_probe)
    assert all(row["writer_open_attempts"] == [] for row in invalid_probe)
    if comm.rank == 0:
        partial_effective = (
            shared_root
            / "identity_write_failure"
            / "numerical_output"
            / "effective_output_config.json"
        )
        assert partial_effective.is_file()
        assert not (
            shared_root
            / "identity_write_failure"
            / "numerical_output"
            / "output_sampling_identity.json"
        ).exists()
        assert (evidence_root / "output_probe_writer_contract.json").is_file()
