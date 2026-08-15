from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.persistent_residual_one_vector import (
    W11A_SCHEMA,
    measure_rank_one_projection,
    repeat_rank_one_projection,
    run_persistent_residual_diagnostic,
    validate_w11a_architecture,
    validate_w11a_authorities,
)


def _architecture() -> dict[str, object]:
    return {
        "fine_space": "uncondensed_fullspace",
        "global_matrix_materialized": False,
        "augmented_matrix_materialized": False,
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "physical_ksp_used": False,
        "pde_used": False,
    }


def _authority() -> dict[str, object]:
    digest = "a" * 64
    source = "b" * 40
    vector = {
        "rows": 4,
        "shape": [4],
        "dtype": "complex128",
        "array_sha256": digest,
        "file_sha256": digest,
    }
    return {
        "source_sha": source,
        "q": dict(vector),
        "target": dict(vector),
        "m3y": {
            "source_sha256": source,
            "manifest_sha256": digest,
            "evidence_sha256": digest,
        },
        "m6a": {"source_sha256": source},
        "layout": {"rows": 4, "dtype": "complex128", "mpi_size": 1},
        "mpc": {
            "owner_local": True,
            "homogenized": True,
            "packing": "fullspace_mpc",
        },
    }


def test_complex_rank_one_projection_repeat_and_scale_invariance() -> None:
    direction = np.array([1 + 2j, -2 + 1j, 3 - 1j, 2 + 0.5j], dtype=np.complex128)
    residual = 1.75j * direction + np.array(
        [2 - 1j, 1 + 3j, -2 + 0.5j, 0.25 - 2j], dtype=np.complex128
    )
    first = repeat_rank_one_projection(residual, direction, block_size=2)
    scaled = measure_rank_one_projection(
        residual, direction * (2 - 3j), block_size=2
    )
    expected = np.vdot(direction, residual) / np.vdot(direction, direction)
    assert np.allclose(first["alpha"], [expected.real, expected.imag], atol=1e-14)
    assert first["repeat_exact"] is True
    assert first["repeat"]["passes"] == 2
    assert first["projection_orthogonality"] <= 1e-14
    assert first["normal_closure"] <= 1e-14
    assert np.isclose(scaled["rho"], first["rho"], rtol=1e-14, atol=1e-14)


def test_rank_one_zero_or_nonfinite_direction_fails_closed() -> None:
    residual = np.array([1 + 0j, 2 - 1j], dtype=np.complex128)
    with pytest.raises(ValueError):
        measure_rank_one_projection(residual, np.zeros(2, dtype=np.complex128))
    bad = residual.copy()
    bad[0] = np.nan + 0j
    with pytest.raises(ValueError):
        measure_rank_one_projection(residual, bad)


def test_w11a_authority_and_architecture_require_fixed_fields() -> None:
    authority = _authority()
    assert validate_w11a_authorities(authority) is True
    authority["layout"] = {"rows": 4, "dtype": "complex128", "mpi_size": 2}
    assert validate_w11a_authorities(authority) is False
    architecture = _architecture()
    assert validate_w11a_architecture(architecture) is True
    del architecture["trace_slab_pc_used"]
    assert validate_w11a_architecture(architecture) is False
    authority = _authority()
    authority["q"]["array_sha256"] = "wrong"
    assert validate_w11a_authorities(authority) is False


def test_w11a_frozen_loader_rechecks_w5_w7_file_and_array_hashes() -> None:
    root = runner.ROOT
    result = runner._m6b_w11a_load_authorities(
        root / runner.M6B_W7_S1_W5_COMPACT_RELATIVE_PATH,
        root / "benchmarks/artifacts/task037_extra_development/m6b_w5_disk_fgmres_41cbbd4_screen_run1",
        root / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
        root / "benchmarks/artifacts/task037_extra_development/m6b_w7_s1_7febc1e_restart_run3",
        "a" * 40,
    )
    assert result["authority"]["q"]["file_sha256"]
    assert result["authority"]["target"]["file_sha256"]
    assert result["q"].dtype == np.dtype(np.complex128)
    assert result["target"].dtype == np.dtype(np.complex128)


def test_w11a_fixed_q0_gate_does_not_call_q1_or_use_target_for_construction() -> None:
    q = np.array([1, 0, 0, 0], dtype=np.complex128)
    target = q.copy()
    calls: list[tuple[str, object]] = []

    def b0_apply(value: np.ndarray) -> np.ndarray:
        calls.append(("b0_apply", value.copy()))
        return value.copy()

    def b0_solve(_max_it: int) -> dict[str, object]:
        raise AssertionError("Q1 must remain closed when Q0 passes")

    def physical(value: np.ndarray) -> np.ndarray:
        calls.append(("physical", value.copy()))
        return value.copy()

    result = run_persistent_residual_diagnostic(
        q,
        target,
        b0_apply=b0_apply,
        physical_action=physical,
        b0_solve=b0_solve,
        architecture=_architecture(),
        predicted_live_set_bytes=1_000_000_000,
    )
    assert result["selected_level"] == "Q0"
    assert result["schema"] == W11A_SCHEMA
    assert result["q1"]["status"] == "not_run_gate_satisfied"
    assert result["checks"]["q_projection"] is True
    assert result["checks"]["target_projection"] is True
    assert result["carrier_audit"]["counters"]["physical_action_count"] == 1
    assert np.array_equal(calls[0][1], q)


def test_w11a_q1_escalates_only_after_fixed_20_step_failure() -> None:
    q = np.array([1, 0, 0, 0], dtype=np.complex128)
    target = np.array([3 - 1j, 0, 0, 0], dtype=np.complex128)
    solve_calls: list[int] = []
    b0_inputs: list[np.ndarray] = []
    physical_inputs: list[np.ndarray] = []

    def b0_apply(value: np.ndarray) -> np.ndarray:
        b0_inputs.append(value.copy())
        return np.array([0, 1, 0, 0], dtype=np.complex128)

    def b0_solve(max_it: int) -> dict[str, object]:
        solve_calls.append(max_it)
        return {
            "true_residual": 1.0e-4 if max_it == 20 else 1.0e-9,
            "solution": q.copy(),
            "iterations": max_it,
        }

    def physical(value: np.ndarray) -> np.ndarray:
        physical_inputs.append(value.copy())
        return value.copy()

    result = run_persistent_residual_diagnostic(
        q,
        target,
        b0_apply=b0_apply,
        physical_action=physical,
        b0_solve=b0_solve,
        architecture=_architecture(),
        predicted_live_set_bytes=1_000_000_000,
    )
    assert solve_calls == [20]
    assert len(b0_inputs) == 1 and np.array_equal(b0_inputs[0], q)
    assert result["selected_level"] == "Q1_20"
    assert result["checks"]["q_projection"] is True
    assert len(physical_inputs) == 2
    assert result["carrier_audit"]["counters"]["physical_action_count"] == 2
    assert result["formal_pass"] is False
    assert result["pde_pass"] is False


def test_w11a_q1_100_is_only_fixed_escalation_and_failure_is_controlled() -> None:
    q = np.array([1, 0, 0, 0], dtype=np.complex128)
    calls: list[int] = []

    def bad_apply(_value: np.ndarray) -> np.ndarray:
        return np.array([0, 1, 0, 0], dtype=np.complex128)

    def bad_solve(max_it: int) -> dict[str, object]:
        calls.append(max_it)
        return {
            "true_residual": 1.0e-2 if max_it == 20 else 1.0e-7,
            "solution": q.copy(),
        }

    result = run_persistent_residual_diagnostic(
        q,
        q,
        b0_apply=bad_apply,
        physical_action=lambda value: value.copy(),
        b0_solve=bad_solve,
        architecture=_architecture(),
        predicted_live_set_bytes=1_000_000_000,
    )
    assert calls == [20, 100]
    assert result["status"] == "gate_failed"
    assert result["classification"] == "W11A_PERSISTENT_DIRECTION_FAIL"
    assert result["problems"] == ["b0_solve_residual"]


def test_w11a_mock_lifecycle_never_overlaps_b0_and_physical_stages() -> None:
    q = np.array([1, 0, 0, 0], dtype=np.complex128)
    architecture_source = inspect.getsource(runner._run_m6b_w11a_diagnostic)
    assert "architecture.clear()" in architecture_source
    assert "release_physical()" in architecture_source
    assert '"authority_or_runtime"' in architecture_source

    def run_case(q0_pass: bool) -> list[str]:
        active: str | None = None
        events: list[str] = []
        shared_architecture: dict[str, object] = {}

        def b0_apply(_value: np.ndarray) -> np.ndarray:
            nonlocal active
            assert active in (None, "b0")
            active = "b0"
            events.append("b0_apply")
            return q.copy() if q0_pass else np.array([0, 1, 0, 0], dtype=np.complex128)

        def b0_solve(max_it: int) -> dict[str, object]:
            nonlocal active
            assert active == "physical"
            events.extend(("release_physical", f"b0_solve_{max_it}"))
            active = "b0"
            return {"true_residual": 1.0e-4, "solution": q.copy()}

        def physical(value: np.ndarray) -> np.ndarray:
            nonlocal active
            assert active == "b0"
            events.append("release_b0")
            active = "physical"
            shared_architecture.clear()
            shared_architecture.update(_architecture())
            events.append("physical")
            return value.copy()

        result = run_persistent_residual_diagnostic(
            q,
            q,
            b0_apply=b0_apply,
            physical_action=physical,
            b0_solve=b0_solve,
            architecture=shared_architecture,
            predicted_live_set_bytes=1_000_000_000,
        )
        assert result["checks"]["architecture"] is True
        return events

    assert run_case(True) == ["b0_apply", "release_b0", "physical"]
    assert run_case(False) == [
        "b0_apply",
        "release_b0",
        "physical",
        "release_physical",
        "b0_solve_20",
        "release_b0",
        "physical",
    ]


def test_w11a_parser_dispatch_has_no_action_or_pde_side_effect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    observed: dict[str, object] = {}
    runner_source = inspect.getsource(runner._run_m6b_w11a_diagnostic)

    def fake(*args: object) -> int:
        observed["args"] = args
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w11a_diagnostic", fake)
    source = "a" * 40
    command = [
        "m6b-w11a-diagnostic",
        "--run-dir", str(tmp_path / "run"),
        "--w5-compact", str(tmp_path / "w5.json"),
        "--w5-raw-dir", str(tmp_path / "w5"),
        "--w7-compact", str(tmp_path / "w7.json"),
        "--w7-raw-dir", str(tmp_path / "w7"),
        "--m3y-manifest", str(tmp_path / "m3y.json"),
        "--jit-cache-source", str(tmp_path / "jit"),
        "--b0-jit-cache-source", str(tmp_path / "b0-jit"),
        "--expected-source-sha", source,
    ]
    assert runner.main(command) == 17
    assert len(observed["args"]) == 9
    assert observed["args"][7] == (tmp_path / "b0-jit").resolve()
    assert "run_persistent_residual_diagnostic" in runner_source
    assert "M6B_W6A_JIT_INVENTORY_SHA256" not in runner_source
    assert "petsc4py" not in inspect.getsource(
        run_persistent_residual_diagnostic
    )


def test_w11a_scope_and_prediction_are_derived_not_formal() -> None:
    scope = runner._m6b_w11a_scope()
    prediction = runner._m6b_w11a_predicted_live_set()
    assert scope["beta"] == 0.0
    assert scope["shifted_pc_used"] is False
    assert scope["target_used_for_construction"] is False
    assert scope["parameter_scan"] is False
    assert prediction["derived_not_measured"] is True
    assert prediction["components"]["m5_process_tree_calibrated_peak_bytes"] == 1_183_698_944
    assert prediction["bytes"] == 1_272_714_790
    assert prediction["bytes"] == runner.M6B_W11A_PREDICTED_LIVE_SET_BYTES
    assert prediction["gate"] is True


def _configure_jit_fixture(
    monkeypatch: pytest.MonkeyPatch,
    h2b: object,
    physical: Path,
    b0: Path,
    b0_names: tuple[str, ...],
    *,
    union_sha: str | None = None,
) -> None:
    physical_record = runner._m6b_w6a_cache_record(h2b, physical)
    b0_record = runner._m6b_w6a_cache_record(h2b, b0)
    if union_sha is None:
        union_sha = runner._m6b_w11a_union_cache_record(
            h2b, physical_record, b0_record
        )["inventory_sha256"]
    monkeypatch.setattr(runner, "M6B_W11A_PHYSICAL_JIT_SOURCE_PATH", physical.resolve())
    monkeypatch.setattr(runner, "M6B_W11A_B0_JIT_SOURCE_PATH", b0.resolve())
    monkeypatch.setattr(runner, "M6B_W11A_PHYSICAL_JIT_INVENTORY_SHA256", physical_record["inventory_sha256"])
    monkeypatch.setattr(runner, "M6B_W11A_B0_JIT_INVENTORY_SHA256", b0_record["inventory_sha256"])
    monkeypatch.setattr(runner, "M6B_W11A_UNION_JIT_INVENTORY_SHA256", union_sha)
    monkeypatch.setattr(runner, "M6B_W11A_PHYSICAL_JIT_FILE_COUNT", len(physical_record["entries"]))
    monkeypatch.setattr(runner, "M6B_W11A_B0_JIT_FILE_COUNT", len(b0_record["entries"]))
    monkeypatch.setattr(
        runner,
        "M6B_W11A_UNION_JIT_FILE_COUNT",
        len(physical_record["entries"]) + len(b0_record["entries"]),
    )
    monkeypatch.setattr(runner, "M6B_W11A_B0_JIT_FILE_NAMES", b0_names)


def _make_jit_fixture(
    tmp_path: Path,
    physical_names: tuple[str, ...] = ("a.c", "a.o"),
    b0_names: tuple[str, ...] = ("b.c", "b.o"),
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    physical = tmp_path / "physical"
    b0 = tmp_path / "b0"
    physical.mkdir()
    b0.mkdir()
    for index, name in enumerate(physical_names):
        (physical / name).write_bytes(f"physical-{index}".encode())
    for index, name in enumerate(b0_names):
        (b0 / name).write_bytes(f"b0-{index}".encode())
    return physical, b0


def test_w11a_dual_jit_stage_merges_atomically_and_records_union(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    physical, b0 = _make_jit_fixture(tmp_path)
    b0_names = tuple(sorted(item.name for item in b0.iterdir()))
    _configure_jit_fixture(monkeypatch, h2b, physical, b0, b0_names)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    audit = runner._m6b_w11a_stage_dual_jit_cache(
        h2b, run_dir, physical, b0
    )
    assert audit["physical_file_count"] == 2
    assert audit["b0_file_count"] == 2
    assert audit["union_file_count"] == 4
    assert audit["warm_precompiled"] is True
    assert audit["runtime_compile_allowed"] is False
    assert audit["union_target_before"]["exists"] is False
    assert not (run_dir / ".jit_cache_staging").exists()
    verified = runner._m6b_w11a_verify_dual_jit_cache(
        h2b, physical, b0, run_dir / "jit_cache", "test"
    )
    assert verified["target_matches_union"] is True
    assert {p.name for p in (run_dir / "jit_cache").iterdir()} == {
        "a.c", "a.o", "b.c", "b.o"
    }


def test_w11a_dual_jit_stage_rejects_inventory_missing_collision_and_existing_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h2b = __import__("benchmarks.run_task037_extra_h2b", fromlist=["*"])
    physical, b0 = _make_jit_fixture(tmp_path / "valid")
    b0_names = tuple(sorted(item.name for item in b0.iterdir()))
    _configure_jit_fixture(monkeypatch, h2b, physical, b0, b0_names)
    (physical / "a.c").write_bytes(b"tampered")
    bad_run = tmp_path / "bad_inventory"
    bad_run.mkdir()
    with pytest.raises(ValueError, match="inventory"):
        runner._m6b_w11a_stage_dual_jit_cache(
            h2b, bad_run, physical, b0
        )

    missing_physical, missing_b0 = _make_jit_fixture(
        tmp_path / "missing", b0_names=("b.c",)
    )
    _configure_jit_fixture(
        monkeypatch, h2b, missing_physical, missing_b0, b0_names
    )
    missing_run = tmp_path / "missing_run"
    missing_run.mkdir()
    with pytest.raises(ValueError, match="inventory"):
        runner._m6b_w11a_stage_dual_jit_cache(
            h2b, missing_run, missing_physical, missing_b0
        )

    collision_physical, collision_b0 = _make_jit_fixture(
        tmp_path / "collision", physical_names=("b.c", "a.o")
    )
    collision_names = tuple(sorted(item.name for item in collision_b0.iterdir()))
    _configure_jit_fixture(
        monkeypatch,
        h2b,
        collision_physical,
        collision_b0,
        collision_names,
        union_sha="0" * 64,
    )
    collision_run = tmp_path / "collision_run"
    collision_run.mkdir()
    with pytest.raises(ValueError, match="collide"):
        runner._m6b_w11a_stage_dual_jit_cache(
            h2b, collision_run, collision_physical, collision_b0
        )

    good_physical, good_b0 = _make_jit_fixture(tmp_path / "existing")
    good_names = tuple(sorted(item.name for item in good_b0.iterdir()))
    _configure_jit_fixture(monkeypatch, h2b, good_physical, good_b0, good_names)
    existing_run = tmp_path / "existing_run"
    existing_run.mkdir()
    (existing_run / "jit_cache").mkdir()
    with pytest.raises(FileExistsError):
        runner._m6b_w11a_stage_dual_jit_cache(
            h2b, existing_run, good_physical, good_b0
        )


def test_w11a_dual_jit_constants_bind_real_authorities() -> None:
    assert runner.M6B_W11A_PHYSICAL_JIT_FILE_COUNT == 36
    assert runner.M6B_W11A_B0_JIT_FILE_COUNT == 4
    assert runner.M6B_W11A_UNION_JIT_FILE_COUNT == 40
    assert runner.M6B_W11A_PHYSICAL_JIT_INVENTORY_SHA256 == (
        "89b34d252e15883d675fe37e207578d93310a1b43516dc6f4280923c46f6f688"
    )
    assert runner.M6B_W11A_B0_JIT_INVENTORY_SHA256 == (
        "370aab13593ed2014777a84c98a180815c85e07864f39e78febb3abf9b36534a"
    )
    assert runner.M6B_W11A_UNION_JIT_INVENTORY_SHA256 == (
        "4a53fb7385d2e58b7448ac2d0e4feb817e1c061455c3dbde68924213e44b4be4"
    )
