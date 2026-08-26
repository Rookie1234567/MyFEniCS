from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
from src.solvers.hybrid_route_c import (
    ROUTE_C_CHECKPOINTS,
    ROUTE_C_LABELS,
    RouteCCollectiveCallbackError,
    _resource_allows_conditional_256,
    classify_route_c_signal,
    run_route_c_online_fgmres,
)
from src.solvers.hybrid_bare_f_authority import compact_gamma_values_for_vector


def _diagonal_operator(size: int, *, identity: bool = False) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ([size, size], comm=PETSc.COMM_SELF)
    matrix.setUp()
    for index in range(size):
        value = 1.0 if identity else 1.0 + 0.01 * index
        matrix[index, index] = value
    matrix.assemble()
    return matrix


def _rhs_pair(size: int) -> dict[str, PETSc.Vec]:
    values = {}
    for label, scale in zip(ROUTE_C_LABELS, (1.0, 2.0), strict=True):
        vector = PETSc.Vec().createSeq(size, comm=PETSc.COMM_SELF)
        vector.set(scale)
        vector.assemble()
        values[label] = vector
    return values


def test_route_c_signal_classifier_keeps_no_signal_and_shared_direction() -> None:
    records = {
        label: {
            "checkpoints": {
                "64": {"true_residual_relative": 0.99},
                "128": {"true_residual_relative": 0.98},
            }
        }
        for label in ROUTE_C_LABELS
    }
    no_signal = classify_route_c_signal(records)
    assert no_signal["classification"] == "ROUTE_C_NO_SIGNAL"
    assert no_signal["terminal"] is True
    assert no_signal["next_action"] == "stop_current_coupled_response_family"
    shared = classify_route_c_signal(records, shared_slow_direction_count=1)
    assert shared["classification"] == "ROUTE_C_WEAK_POSITIVE_SIGNAL"
    assert shared["terminal"] is False
    assert shared["next_action"] == "bounded_online_rank_screen"


def test_route_c_runs_continuous_sources_with_deduplicated_checkpoints() -> None:
    operator = _diagonal_operator(256)
    rhs = _rhs_pair(256)
    initial_values = {
        label: np.array(vector.array_r, copy=True) for label, vector in rhs.items()
    }
    checkpoint_rows: list[dict[str, object]] = []
    basis_calls: list[tuple[str, int, int]] = []

    def resource() -> dict[str, object]:
        return {
            "status": "controlled_test_stop",
            "pass": False,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
        }

    def interface(residual: PETSc.Vec, _rhs: PETSc.Vec, iteration: int):
        norm = float(residual.norm())
        return {"lower": norm, "upper": norm, "iteration": iteration}

    def interface_direction(
        _label: str,
        _restart: int,
        _direction_index: int,
        _residual_direction: PETSc.Vec,
        _response_direction: PETSc.Vec,
        _metadata: dict[str, object],
    ):
        values = np.asarray(
            _response_direction.getArray(readonly=True), dtype=np.complex128
        ).copy()
        shard = {
            "values": values,
            "canonical_positions": np.arange(
                len(values), dtype=np.int64
            ),
            "canonical_key_count": len(values),
            "canonical_key_order_sha256": "a" * 64,
        }
        return {
            "lower": dict(shard),
            "upper": dict(shard),
            "audit": {
                "status": "pass",
                "replicated": False,
                "source_direction": "preconditioned_response_direction_Z_y",
                "canonical_interface_trace": {
                    "lower": {"status": "pass"},
                    "upper": {"status": "pass"},
                },
            },
        }

    def basis(
        label: str,
        restart: int,
        direction_index: int,
        residual_direction: PETSc.Vec,
        response_direction: PETSc.Vec,
        _metadata: dict[str, object],
    ):
        basis_calls.append((label, restart, direction_index))
        return {
            "status": "pass",
            "local_norm": float(residual_direction.norm()),
            "response_local_norm": float(response_direction.norm()),
            "owner_local": True,
            "replicated": False,
            "residual_direction": {"kind": "residual_space_V_y"},
            "preconditioned_response_direction": {"kind": "response_space_Z_y"},
        }

    try:
        result = run_route_c_online_fgmres(
            operator,
            rhs,
            right_preconditioner=None,
            allow_identity_test_only=True,
            resource_callback=resource,
            interface_residual_callback=interface,
            interface_direction_callback=interface_direction,
            checkpoint_callback=lambda row: checkpoint_rows.append(dict(row)),
            basis_callback=basis,
        )
        assert result["labels"] == list(ROUTE_C_LABELS)
        assert result["restart"] == 32
        assert result["continuous_right_fgmres"] is True
        assert result["conditional_checkpoint"] == 256
        assert result["conditional_256_gate"]["per_source"] == {
            label: {
                "authorized": False,
                "final_iteration": 128,
                "completed": False,
            }
            for label in ROUTE_C_LABELS
        }
        assert result["conditional_256_gate"]["aggregate_pass"] is False
        assert result["conditional_256_gate"]["aggregate_completed"] is False
        assert result["exact_output_vectors_consumed"] == 0
        assert result["full_side_exact_factor_count"] == 0
        assert (
            result["numeric_collective_inventory"][
                "fe_sized_numeric_allgather_count"
            ]
            == 0
        )
        assert result["numeric_collective_inventory"]["owner_row_basis_replicated"] is False
        for label in ROUTE_C_LABELS:
            row = result["records"][label]
            assert row["continuous_right_fgmres"] is True
            assert row["restart"] == 32
            assert row["iterations"] == 128
            assert row["authorized_max"] == 128
            assert row["stopped_at_happy_breakdown"] is False
            assert row["checkpoint_callback_count"] == len(ROUTE_C_CHECKPOINTS)
            assert set(row["checkpoints"]) >= {
                str(checkpoint) for checkpoint in ROUTE_C_CHECKPOINTS
            }
            assert row["conditional_256_authorized"] is False
            assert row["conditional_256_completed"] is False
            assert row["resource_at_128"]["collective_pass"] is False
            for restart in row["direction_records"]:
                assert restart["direction_count"] <= 8
                assert np.isfinite(restart["orthogonality_error"])
                assert np.isfinite(restart["arnoldi_relation_residual"])
                for direction in restart["directions"]:
                    assert direction["kind"] == "owner_row_harmonic_ritz_direction"
                    assert np.isfinite(direction["ritz_residual_estimate"])
                    assert np.isfinite(direction["full_action_residual_relative"])
                    assert direction["interface_direction_projection"]["status"] == (
                        "pass"
                    )
        checkpoint_keys = Counter(
            (str(row["label"]), int(row["iteration"])) for row in checkpoint_rows
        )
        assert checkpoint_keys == Counter(
            (label, checkpoint)
            for label in ROUTE_C_LABELS
            for checkpoint in ROUTE_C_CHECKPOINTS
        )
        assert len(basis_calls) == sum(
            len(direction["directions"])
            for record in result["direction_records"].values()
            for direction in record
        )
        assert all(row["continuous"] is True for row in checkpoint_rows)
        assert all(
            row["interface_residual_trace"]["lower"] >= 0.0
            for row in checkpoint_rows
        )
        assert result["shared_slow_directions"]["stable_components"]
        serialized = str(result)
        assert "canonical_positions" not in serialized
        assert all(
            "artifacts" not in row["interface_residual_trace"]
            for row in checkpoint_rows
        )
        for label, values in initial_values.items():
            np.testing.assert_array_equal(values, rhs[label].array_r)
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_happy_breakdown_never_crosses_authorized_128() -> None:
    operator = _diagonal_operator(4, identity=True)
    rhs = _rhs_pair(4)
    try:
        result = run_route_c_online_fgmres(
            operator,
            rhs,
            allow_identity_test_only=True,
            resource_callback=lambda: {
                "pass": True,
                "rss_bytes": 1,
                "swap_bytes": 0,
                "wall_controlled": True,
            },
        )
        for label in ROUTE_C_LABELS:
            assert result["records"][label]["iterations"] == 1
            assert result["records"][label]["iterations"] <= 128
            assert result["records"][label]["stopped_at_happy_breakdown"] is True
            assert (
                result["records"][label]["final_true_residual_relative"]
                <= 1.0e-10
            )
            assert result["records"][label]["conditional_256_authorized"] is False
            assert result["records"][label]["resource_at_128"] is None
        assert result["signal"]["classification"] == "ROUTE_C_STRONG_SIGNAL"
        assert result["signal"]["terminal"] is False
        assert result["signal"]["next_action"] == "bounded_online_rank_screen"
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_wall_helper_is_the_conditional_256_gate_input() -> None:
    first = level_a._route_c_wall_observation(
        formal_elapsed_seconds=6000.0,
        krylov_elapsed_seconds=5000.0,
        last_krylov_elapsed_seconds=None,
        observation_index=0,
    )
    assert first["elapsed_seconds"] == 6000.0
    assert first["predicted_remaining_seconds"] == 15000.0
    assert first["predicted_total_seconds"] == 21000.0
    assert _resource_allows_conditional_256(
        {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": first,
        }
    )
    incomplete = dict(first)
    incomplete.pop("predicted_remaining_seconds")
    assert not _resource_allows_conditional_256(
        {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": incomplete,
        }
    )
    tampered = dict(first, predicted_total_seconds=3.0)
    assert not _resource_allows_conditional_256(
        {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": tampered,
        }
    )

    second = level_a._route_c_wall_observation(
        formal_elapsed_seconds=13000.0,
        krylov_elapsed_seconds=12000.0,
        last_krylov_elapsed_seconds=5000.0,
        observation_index=1,
    )
    assert second["interval_since_previous_128_seconds"] == 7000.0
    assert second["predicted_remaining_seconds"] == 7000.0
    assert second["predicted_total_seconds"] == 20000.0
    assert _resource_allows_conditional_256(
        {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": second,
        }
    )

    rejected = level_a._route_c_wall_observation(
        formal_elapsed_seconds=21500.0,
        krylov_elapsed_seconds=12000.0,
        last_krylov_elapsed_seconds=5000.0,
        observation_index=1,
    )
    assert rejected["pass"] is False
    assert not _resource_allows_conditional_256(
        {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": rejected,
        }
    )


def test_route_c_interface_callback_failure_cleans_direction_and_preserves_root() -> None:
    operator = _diagonal_operator(8)
    rhs = _rhs_pair(8)
    captured: dict[str, PETSc.Vec] = {}

    def failing_interface_direction(*args: object) -> object:
        captured["direction"] = args[3]
        captured["response_direction"] = args[4]
        raise ValueError("unexpected interface callback shape")

    try:
        with pytest.raises(
            RouteCCollectiveCallbackError, match="unexpected interface callback shape"
        ):
            run_route_c_online_fgmres(
                operator,
                rhs,
                allow_identity_test_only=True,
                interface_direction_callback=failing_interface_direction,
            )
        assert bool(captured["direction"]) is False
        assert int(captured["direction"].handle) == 0
        assert bool(captured["response_direction"]) is False
        assert int(captured["response_direction"].handle) == 0
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_watchdog_plan_uses_route_c_resource_contract() -> None:
    plan = watchdog.build_task040_level_a_watchdog_plan(
        input_path=Path("input.dat"),
        exact_spool_root=Path("frozen"),
        run_directory=Path("fresh-route-c-watchdog"),
        source_sha="a" * 40,
        v5_route_c=True,
    )
    assert plan["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert plan["watchdog"]["swap_limit_bytes"] == 0
    assert plan["timeout_seconds"] == 21600
    assert plan["watchdog"]["process_group"] is True
    assert plan["watchdog"]["bottom_route_only"] is True


def test_route_c_resource_preflight_uses_45_gib_and_swap_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        level_a,
        "wsl_memory_snapshot",
        lambda: {"mem_available_bytes": 50 * 2**30},
    )
    monkeypatch.setattr(
        level_a.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=21 * 2**30),
    )
    monkeypatch.setattr(
        level_a,
        "_worker_current_resource",
        lambda _comm, hard_limit_bytes: {
            "pass": True,
            "all_status_readable": True,
            "swap_bytes": 0,
            "hard_limit_bytes": hard_limit_bytes,
        },
    )
    result = level_a._route_c_resource_preflight(MPI.COMM_SELF, tmp_path)
    assert result["pass"] is True
    assert result["hard_stop_bytes"] == 45 * 2**30
    assert result["minimum_mem_available_bytes"] == 49 * 2**30
    assert result["swap_limit_bytes"] == 0
    assert result["timeout_seconds"] == 21600
    assert result["ranks"][0]["swap_bytes"] == 0


def test_route_c_qep_and_external_contract_use_observed_inventory() -> None:
    inventory = {
        "qep_calls": 0,
        "minimal_external_coupling_objects_constructed": 1,
        "minimal_external_surface_component_count": 2,
        "minimal_external_coupling_construction_call_count": 2,
        "minimal_external_component_instances_total": 4,
        "minimal_external_peak_live_components": 2,
        "minimal_external_coupling_kind_count": 1,
    }
    assert level_a._route_c_observed_qep_calls(inventory) == 0
    contract = level_a._route_c_observed_external_contract(
        inventory,
        {"C": 0, "D": 0, "H": 0},
    )
    assert contract["pass"] is True
    assert contract["observed"][
        "minimal_external_coupling_construction_call_count"
    ] == 2
    with pytest.raises(RuntimeError, match="observed qep_calls=1"):
        level_a._route_c_observed_qep_calls(dict(inventory, qep_calls=1))
    with pytest.raises(RuntimeError, match="minimal external RHS inventory"):
        level_a._route_c_observed_external_contract(
            dict(inventory, minimal_external_component_instances_total=3),
            {"C": 0, "D": 0, "H": 0},
        )


def test_route_c_runner_dispatch_is_opt_in_with_mocked_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_route(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "mocked",
            "artifact_index_by_rank": [{"rank": 0}],
            "group_pc": {"factor_lifecycle": {"construction_count": 3}},
        }

    monkeypatch.setattr(level_a, "_run_v5_route_c", fake_route)
    result = level_a.run_task040_level_a(
        object(),
        SimpleNamespace(bottom_interface_nm=1.0, top_interface_nm=2.0),
        comm=MPI.COMM_SELF,
        exact_spool_root=tmp_path / "frozen",
        run_directory=tmp_path / "fresh",
        source_sha="a" * 40,
        input_path=tmp_path / "input.dat",
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        v5_route_c=True,
    )
    assert result["status"] == "mocked"
    assert captured["run_directory"] == tmp_path / "fresh"
    assert captured["exact_spool_root"] == tmp_path / "frozen"
    assert captured["watchdog_enabled"] is False


def test_route_c_runner_records_observed_lifecycle_and_all_rank_artifacts() -> None:
    ready = {
        "factor_count_ready": 3,
        "destroyed": False,
        "action_destroyed": False,
    }
    after = {
        "factor_count_ready": 0,
        "factor_count_after_cleanup": 0,
        "destroyed": True,
        "action_destroyed": True,
    }
    lifecycle = level_a._route_c_observed_group_factor_lifecycle(ready, after)
    assert lifecycle["construction_count"] == 3
    assert lifecycle["destruction_count"] == 3
    assert lifecycle["simultaneous_factor_count_max"] == 3
    assert lifecycle["pc_setup_count"] == 1
    assert lifecycle["continuous_source_solve_count"] == 2
    action_not_destroyed = dict(after, action_destroyed=False)
    with pytest.raises(RuntimeError, match="action was not observed destroyed"):
        level_a._route_c_observed_group_factor_lifecycle(ready, action_not_destroyed)

    artifact_index = level_a._route_c_all_rank_artifact_index(
        rank_count=2,
        source_records_by_rank=[{"rank": 0}, {"rank": 1}],
        gamma_layouts_by_rank=[{"rank": 0}, {"rank": 1}],
        canonical_active_layouts_by_rank=[{"rank": 0}, {"rank": 1}],
        interface_trace_artifacts_by_rank=[{"rank": 0}, {"rank": 1}],
        basis_artifacts_by_rank=[{"rank": 0}, {"rank": 1}],
    )
    assert [item["rank"] for item in artifact_index] == [0, 1]
    assert artifact_index[1]["basis_artifacts"] == {"rank": 1}
    with pytest.raises(ValueError, match="one entry per MPI rank"):
        level_a._route_c_all_rank_artifact_index(
            rank_count=2,
            source_records_by_rank=[{"rank": 0}],
            gamma_layouts_by_rank=[{"rank": 0}, {"rank": 1}],
            canonical_active_layouts_by_rank=[{"rank": 0}, {"rank": 1}],
            interface_trace_artifacts_by_rank=[{"rank": 0}, {"rank": 1}],
            basis_artifacts_by_rank=[{"rank": 0}, {"rank": 1}],
        )


def test_route_c_mpi_owner_uses_actual_owner_local_compact_gamma_shards() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (2, 4):
        pytest.skip("run this owner-local contract with mpiexec -n 2 or -n 4")
    global_size = 2 * comm.size
    vector = PETSc.Vec().createMPI((PETSc.DECIDE, global_size), comm=comm)
    try:
        first, last = map(int, vector.getOwnershipRange())
        rows = np.arange(first, last, dtype=np.int64)
        vector.array[:] = np.asarray(
            [10.0 + float(row) + 0.5j * float(comm.rank) for row in rows],
            dtype=np.complex128,
        )
        vector.assemble()
        layout = SimpleNamespace(
            canonical_keys=tuple(f"k{index}" for index in range(global_size)),
            blocks=(
                SimpleNamespace(
                    block=SimpleNamespace(
                        raw_row_ids=rows,
                        raw_to_canonical=np.eye(len(rows), dtype=np.complex128),
                    ),
                    positions=rows,
                ),
            ),
        )
        shard = compact_gamma_values_for_vector(vector, layout)
        assert shard["canonical_positions"].tolist() == rows.tolist()
        np.testing.assert_allclose(shard["values"], vector.array_r)
        owner_records = comm.allgather(
            (
                (first, last),
                tuple(int(row) for row in shard["canonical_positions"]),
                tuple(complex(value) for value in shard["values"]),
            )
        )
        ownership = [item[0] for item in owner_records]
        assert ownership == sorted(ownership)
        assert ownership[0][0] == 0
        assert ownership[-1][1] == global_size
        assert all(left[1] == right[0] for left, right in zip(ownership, ownership[1:]))
        assert [
            row for _ownership, rows_, _values in owner_records for row in rows_
        ] == list(range(global_size))
        assert all(
            len(item[2]) == item[0][1] - item[0][0] for item in owner_records
        )
        assert shard["values"].size == vector.getLocalSize()
    finally:
        vector.destroy()


def test_route_c_mpi_owner_runs_distributed_fgmres_collectives() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (2, 4):
        pytest.skip("run this distributed Route C smoke with mpiexec -n 2 or -n 4")
    global_size = 2 * comm.size
    operator = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, global_size), (PETSc.DECIDE, global_size)),
        nnz=1,
        comm=comm,
    )
    operator.setUp()
    first, last = map(int, operator.getOwnershipRange())
    for row in range(first, last):
        operator[row, row] = 1.0
    operator.assemble()
    rhs = {
        label: operator.createVecRight()
        for label in ROUTE_C_LABELS
    }
    initial_values: dict[str, np.ndarray] = {}
    try:
        for index, label in enumerate(ROUTE_C_LABELS):
            rhs[label].array[:] = np.asarray(
                1.0 + index + np.arange(last - first),
                dtype=np.complex128,
            )
            rhs[label].assemble()
            initial_values[label] = rhs[label].array_r.copy()
        result = run_route_c_online_fgmres(
            operator,
            rhs,
            allow_identity_test_only=True,
        )
        classification = result["signal"]["classification"]
        assert comm.allgather(classification) == [classification] * comm.size
        assert result["numeric_collective_inventory"][
            "fe_sized_numeric_allgather_count"
        ] == 0
        assert result["right_preconditioner"]["identity_test_only"] is True
        for label in ROUTE_C_LABELS:
            row = result["records"][label]
            assert row["iterations"] == 1
            assert row["final_iteration"] == 1
            assert row["final_true_residual_relative"] <= 1.0e-12
            np.testing.assert_array_equal(rhs[label].array_r, initial_values[label])
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_conditional_256_requires_and_records_explicit_wall_observation() -> None:
    operator = _diagonal_operator(512)
    rhs = _rhs_pair(512)
    interface_iterations: list[int] = []
    checkpoint_rows: list[dict[str, object]] = []

    def interface_trace(
        residual: PETSc.Vec,
        _rhs: PETSc.Vec,
        iteration: int,
    ) -> dict[str, float]:
        interface_iterations.append(int(iteration))
        value = float(residual.norm())
        return {component: value for component in ("lower", "upper", "joint")}

    def resource() -> dict[str, object]:
        return {
            "pass": True,
            "rss_bytes": 1,
            "swap_bytes": 0,
            "wall_controlled": True,
            "wall_observation": {
                "budget_seconds": 21600.0,
                "elapsed_seconds": 1.0,
                "remaining_seconds": 21599.0,
                "predicted_remaining_seconds": 1.0,
                "predicted_total_seconds": 2.0,
                "pass": True,
            },
        }

    try:
        result = run_route_c_online_fgmres(
            operator,
            rhs,
            allow_identity_test_only=True,
            resource_callback=resource,
            interface_residual_callback=interface_trace,
            checkpoint_callback=lambda row: checkpoint_rows.append(dict(row)),
        )
        for label in ROUTE_C_LABELS:
            row = result["records"][label]
            assert row["conditional_256_authorized"] is True
            assert row["conditional_256_completed"] is True
            assert row["final_iteration"] == 256
            assert "256" in row["checkpoints"]
            assert row["checkpoints"]["256"]["finite"] is True
            assert set(row["checkpoints"]["256"]["interface_residual_trace"]) == {
                "lower",
                "upper",
                "joint",
            }
            assert row["checkpoint_callback_count"] == 5
        assert interface_iterations.count(256) == len(ROUTE_C_LABELS)
        assert sum(row["iteration"] == 256 for row in checkpoint_rows) == len(
            ROUTE_C_LABELS
        )
        gate = result["conditional_256_gate"]
        assert gate["authorized_pass"] is True
        assert gate["aggregate_pass"] is True
        assert gate["aggregate_completed"] is True
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_compact_gamma_applies_nontrivial_canonical_transform() -> None:
    vector = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    vector.array[:] = np.asarray([1.0 + 2.0j, 3.0 - 1.0j, 7.0, 11.0])
    vector.assemble()
    transform = np.asarray(
        [[0.0 + 1.0j, 2.0 + 0.0j], [-1.0 + 0.0j, 0.5 + 0.0j]],
        dtype=np.complex128,
    )
    layout = SimpleNamespace(
        canonical_keys=("a", "b", "c"),
        blocks=(
            SimpleNamespace(
                block=SimpleNamespace(
                    raw_row_ids=np.asarray([0, 1], dtype=np.int64),
                    raw_to_canonical=transform,
                ),
                positions=np.asarray([2, 0], dtype=np.int64),
            ),
        ),
    )
    try:
        shard = compact_gamma_values_for_vector(vector, layout)
        transformed = transform @ np.asarray(vector.array_r[:2])
        assert shard["canonical_positions"].tolist() == [0, 2]
        np.testing.assert_allclose(
            shard["values"],
            np.asarray([transformed[1], transformed[0]], dtype=np.complex128),
        )
    finally:
        vector.destroy()


def test_route_c_formal_rejects_identity_preconditioner() -> None:
    operator = _diagonal_operator(4)
    rhs = _rhs_pair(4)
    try:
        with pytest.raises(ValueError, match="nonidentity"):
            run_route_c_online_fgmres(operator, rhs)
    finally:
        for vector in rhs.values():
            vector.destroy()
        operator.destroy()


def test_route_c_plan_is_opt_in_and_does_not_enable_exact_factor() -> None:
    plan = level_a.build_task040_level_a_plan(
        input_path=Path("input.dat"),
        exact_spool_root=Path("frozen"),
        run_directory=Path("fresh-route-c"),
        source_sha="a" * 40,
        v5_route_c=True,
    )
    assert plan["v5_route_c"] is True
    assert plan["source_labels"] == list(ROUTE_C_LABELS)
    assert plan["restart"] == 32
    assert plan["checkpoints"] == list(ROUTE_C_CHECKPOINTS)
    assert plan["conditional_checkpoint"] == 256
    assert plan["full_side_exact_factor_count"] == 0
    assert "full_side_exact_factor" in plan["forbidden"]
    assert "full_cross_section_factor" not in plan["forbidden"]
    assert plan["route_c_only"] is True
