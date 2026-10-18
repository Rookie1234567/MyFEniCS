"""Small Task42 direct-path contracts; no mesh, factorization, or PDE is built."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest
from petsc4py import PETSc

import src.solvers.dtn_port_3d as dtn
from src.solvers.full3d_lifecycle_packet import load_packet
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
