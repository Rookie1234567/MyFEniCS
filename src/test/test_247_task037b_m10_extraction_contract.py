from __future__ import annotations

import ast
from datetime import datetime
import json
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from mpi4py import MPI

from benchmarks import run_task037b_hybrid_iterative as runner
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    _apply_columns_marker_detail,
    _replicated_array_marker_detail,
    build_exact_one_cell_traction_matrices,
)


ROOT = Path(__file__).resolve().parents[2]
HEX40 = "a" * 40
HEX64 = "b" * 64


def _argv(*, frozen: bool = True) -> list[str]:
    values = [
        "--case-label",
        "task037b_m10_contract",
        "--run-dir",
        str(ROOT / "benchmarks/artifacts/task037b/m10_contract"),
        "--output",
        str(ROOT / "benchmarks/artifacts/task037b/m10_contract.json"),
        "--verified-clean-sha",
        HEX40,
        "--h1-authority",
        str(ROOT / "h1.json"),
        "--h1-authority-sha256",
        HEX64,
        "--full3d-reference",
        str(ROOT / "full3d.json"),
        "--full3d-reference-sha256",
        HEX64,
        "--task035c-p6-preflight-authority",
        str(ROOT / "p6.json"),
        "--task035c-p6-preflight-sha256",
        HEX64,
    ]
    return (["--frozen-m10"] if frozen else []) + values


def test_parser_is_closed_without_explicit_frozen_profile() -> None:
    with pytest.raises(SystemExit):
        runner.parse_args(_argv(frozen=False))
    args = runner.parse_args(_argv())
    assert args.frozen_m10 is True
    assert args.case_label == "task037b_m10_contract"
    assert args.verified_clean_sha == HEX40
    invalid_h1 = _argv()
    invalid_h1[invalid_h1.index("--h1-authority-sha256") + 1] = "c" * 63
    with pytest.raises(SystemExit):
        runner.parse_args(invalid_h1)


def test_profile_has_one_frozen_mpi8_parameter_set() -> None:
    profile = runner.FROZEN_M10
    assert profile.degree == 6
    assert profile.h_nm == 10.0
    assert profile.modal_degree == 6
    assert profile.modal_h_nm == 10.0
    assert profile.wavelength_nm == 13.5
    assert profile.polarization_kind == "s"
    assert profile.incident_grazing_deg == 10.0
    assert (profile.bottom_interface_nm, profile.top_interface_nm) == (10.0, 110.0)
    assert (profile.requested_modes, profile.candidate_modes) == (120, 240)
    assert profile.dtN_modes_per_endcap == 40
    assert profile.solver_path == "block-ldu-action-full-solve"
    assert profile.subdomain_count == 1
    assert profile.overlap == 0.0
    assert profile.ilu_level == 0
    assert profile.shift == 0.1
    assert profile.near_degenerate_tolerance == 1.0e-6
    assert profile.block_rotation_tolerance == 1.0e-6
    assert profile.restart == 90
    assert profile.max_it == 1000
    assert profile.rtol == 5.0e-9
    assert profile.initial_guess == "zero"
    assert profile.mpi_size == 8


def test_lifecycle_order_is_explicit_and_fail_closed() -> None:
    trace = runner.LifecycleTrace()
    for stage in runner.M10_LIFECYCLE_ORDER:
        trace.record(stage)
    report = trace.as_dict()
    assert report["observed"] == list(runner.M10_LIFECYCLE_ORDER)
    assert report["pass"] is True

    invalid = runner.LifecycleTrace()
    invalid.record("setup")
    with pytest.raises(RuntimeError):
        invalid.record("bottom_recovery")
    with pytest.raises(ValueError):
        invalid.record("old_campaign_disposition")


def test_lifecycle_trace_writes_one_flushed_line_per_stage(tmp_path: Path) -> None:
    path = tmp_path / "memory_stages.jsonl"
    trace = runner.LifecycleTrace(memory_stages=path)
    for stage in runner.M10_LIFECYCLE_ORDER:
        trace.record(stage)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["stage"] for row in rows] == list(runner.M10_LIFECYCLE_ORDER)
    assert len(rows) == len(runner.M10_LIFECYCLE_ORDER)
    assert all("residual" not in row for row in rows)


def test_task039_detail_marker_has_utc_origin_and_rank0_writer(tmp_path: Path) -> None:
    path = tmp_path / "memory_detail_markers.raw.jsonl"
    trace = runner.LifecycleTrace(
        detail_marker_path=path,
        comm=MPI.COMM_WORLD,
    )
    trace.detail("one_cell_factor_ready", {"rows": 12})
    MPI.COMM_WORLD.Barrier()
    rows = None
    if MPI.COMM_WORLD.rank == 0:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows = MPI.COMM_WORLD.bcast(rows, root=0)
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == "task039.v3-memory-detail-marker.v2"
    assert row["marker_type"] == "memory_detail"
    assert datetime.fromisoformat(row["timestamp_utc"]).tzinfo is not None
    assert row["elapsed_origin"] == "worker_lifecycle_detail_started_perf_counter"
    assert row["detail"] == {"rows": 12}


def test_task039_memory_marker_byte_fields_keep_array_scopes_separate() -> None:
    setup_parameters = inspect.signature(runner.build_frozen_m10_setup).parameters
    assert setup_parameters["detail_stage_callback"].default is None
    assert setup_parameters["post_destroy_cleanup"].default is None
    builder_parameters = inspect.signature(
        build_exact_one_cell_traction_matrices
    ).parameters
    assert builder_parameters["stage_callback"].default is None
    assert builder_parameters["post_destroy_cleanup"].default is None

    lift = _replicated_array_marker_detail(
        12, 8, 4, array_scope="replicated_lift_output_combined_left_right"
    )
    assert "distributed_petsc_5mat_payload_lower_bound_bytes" not in lift
    assert lift["replicated_numpy_array_bytes_per_rank"] == 12 * 8 * 16
    assert lift["replicated_numpy_array_bytes_process_tree"] == 4 * 12 * 8 * 16

    apply = _apply_columns_marker_detail(12, 30, 8, 4, direction="forward")
    assert (
        apply["distributed_petsc_5mat_payload_lower_bound_bytes"]
        == (3 * 12 + 2 * 30) * 8 * 16
    )
    assert apply["replicated_input_numpy_bytes_per_rank"] == 12 * 8 * 16
    assert apply["replicated_output_numpy_bytes_per_rank"] == 12 * 8 * 16
    assert "replicated_numpy_array_bytes_per_rank" not in apply


def test_runner_does_not_import_historical_task_runners() -> None:
    tree = ast.parse(inspect.getsource(runner))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "benchmarks.run_task032_phase6_augmented" not in imported_modules
    assert "benchmarks.run_task033_memory_watchdog" not in imported_modules


def test_cleanup_and_canonical_helpers_are_single_path_contracts() -> None:
    cleanup_source = inspect.getsource(runner.collective_heap_cleanup)
    canonical_source = inspect.getsource(runner._write_canonical_manifest_exports)
    assert "PETSc.garbage_cleanup" in cleanup_source
    assert "_trim_process_heap" in cleanup_source
    assert "iter_canonical_active_trace_packets" in canonical_source
    assert "iter_canonical_full_fe_packets" in canonical_source
    assert "audit_packets=True" in canonical_source
    assert "canonical_shard_manifest" in canonical_source
    assert "run_directory" in canonical_source
    assert "extractor_global_packet_count" in canonical_source
    assert "manifest_audit_count_matches" in canonical_source
    assert "role_pass" in canonical_source
    assert '"pass": role_pass' in canonical_source
    assert '"pass": True' not in canonical_source
    assert "del packets" in canonical_source
    signature = inspect.signature(runner._write_canonical_manifest_exports)
    assert signature.parameters["side"].default is inspect.Parameter.empty
    assert 'for side in ("bottom", "top")' not in canonical_source


def test_physical_setup_contract_is_frozen_and_releases_qep_early() -> None:
    setup_source = inspect.getsource(runner.build_frozen_m10_setup)
    assert "build_matching_cross_section" in setup_source
    assert "build_cross_section_spaces" in setup_source
    assert "assemble_quadratic_beta_operators" in setup_source
    assert "PoyntingFluxEvaluator" in setup_source
    assert "analytic_homogeneous_beta" in setup_source
    assert "requested_modes=FROZEN_M10.candidate_modes" in setup_source
    assert "target=-target" in setup_source
    assert 'desired_direction="forward"' in setup_source
    assert 'desired_direction="backward"' in setup_source
    assert (
        "near_degenerate_tolerance=FROZEN_M10.near_degenerate_tolerance" in setup_source
    )
    assert (
        "block_rotation_tolerance=FROZEN_M10.block_rotation_tolerance" in setup_source
    )
    assert "assemble_hybrid_local_dtn_action_system" in setup_source
    assert "build_hybrid_internal_mode_coupling" in setup_source
    runner_source = inspect.getsource(runner)
    assert "benchmarks.run_task032_phase6_augmented" not in runner_source
    assert "benchmarks.run_task033_memory_watchdog" not in runner_source
    for historical_token in ("H5", "R2", "R3", "R5", "V1", "V2", "V3"):
        assert historical_token not in runner_source

    tree = ast.parse(runner_source)
    assemble_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assemble_quadratic_beta_operators"
    ]
    assert len(assemble_calls) == 1
    assert len(assemble_calls[0].args) == 3

    release_source = inspect.getsource(runner.release_frozen_m10_qep_operators)
    assert "operators.destroy()" in release_source
    assert "collective_heap_cleanup(comm)" in release_source
    release_tree = ast.parse(release_source)
    destroy_calls = [
        node
        for node in ast.walk(release_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "destroy"
    ]
    assert len(destroy_calls) == 1
    assert isinstance(destroy_calls[0].func.value, ast.Name)
    assert destroy_calls[0].func.value.id == "operators"

    setup_tree = ast.parse(inspect.getsource(runner.build_frozen_m10_setup))
    release_calls = [
        node
        for node in ast.walk(setup_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "release_frozen_m10_qep_operators"
    ]
    assert len(release_calls) == 1
    release_assignment = next(
        node
        for node in ast.walk(setup_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "operators"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and node.value.value is None
    )
    assert release_calls[0].lineno < release_assignment.lineno

    pair_position = setup_source.index("reciprocal_pairs = pair_reciprocal_mode_bases")
    release_position = setup_source.index(
        "qep_release = release_frozen_m10_qep_operators"
    )
    bottom_position = setup_source.index(
        "bottom = assemble_hybrid_local_dtn_action_system"
    )
    top_position = setup_source.index("top = assemble_hybrid_local_dtn_action_system")
    coupling_position = setup_source.index(
        "coupling = build_hybrid_internal_mode_coupling"
    )
    assert pair_position < release_position < bottom_position < top_position
    assert top_position < coupling_position
    assert "qep_matrices_ready" in setup_source
    assert "modal_qep_temporaries_released" in setup_source
    assert not any(
        isinstance(node, ast.Name)
        and node.id == "operators"
        and node.lineno > release_assignment.lineno
        for node in ast.walk(setup_tree)
    )


def test_linear_stage_is_single_public_frozen_chain_with_ordered_release() -> None:
    source = inspect.getsource(runner.solve_frozen_m10_linear)
    for symbol in (
        "HybridAugmentedLayout",
        "internal_modal_rhs_correction",
        "create_hybrid_assembled_block_action",
        "create_hybrid_local_dtn_action_components",
        "build_hybrid_whole_endcap_fixed_smoother_action",
        "HybridLocalDtnWoodburyFixedAction",
        "create_action_block_ldu_preconditioner",
        "HybridBlockLduIterativeConfig",
        "solve_hybrid_block_ldu_iterative",
    ):
        assert symbol in source
    tree = ast.parse(source)
    solve_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "solve_hybrid_block_ldu_iterative"
    ]
    assert len(solve_calls) == 1
    assert "config=config" in source
    for forbidden in (
        "solve_action_block_ldu_full",
        "screen_action_block_ldu",
        "progressive",
        "Task032",
        "Task033",
    ):
        assert forbidden not in source

    release_source = inspect.getsource(runner._release_frozen_m10_linear_stack)
    release_order = (
        'fixed["bottom"].destroy()',
        'fixed["top"].destroy()',
        'woodbury["bottom"].destroy()',
        'woodbury["top"].destroy()',
        "result.release_deferred_action_modal_schur()",
        'components["bottom"].destroy()',
        'components["top"].destroy()',
        "rhs.destroy()",
        "operator.destroy()",
        "operator_context.destroy(operator)",
    )
    positions = [release_source.index(token) for token in release_order]
    assert positions == sorted(positions)
    assert '"pass": True' not in release_source
    assert '"checks": checks' in release_source
    assert "exception_cleanup" in release_source
    assert "block_ldu_context_contract" in release_source
    assert "action_modal_schur_retained_after_pc_destroyed" in source
    assert "action_modal_schur_released" in source


def test_recovery_stage_is_two_side_fail_closed_and_ordered() -> None:
    side_source = inspect.getsource(runner._recover_frozen_m10_side)
    assert "recover_petsc_auxiliary" in side_source
    assert "recover_hybrid_static_local_field" in side_source
    side_tree = ast.parse(side_source)
    for name in ("recover_petsc_auxiliary", "recover_hybrid_static_local_field"):
        calls = [
            node
            for node in ast.walk(side_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        assert len(calls) == 1
    assert "auxiliary_vec.destroy()" in side_source
    assert "auxiliary_override=auxiliary" in side_source
    assert "max(h_q_norm, rhs_norm, 1.0e-30)" in side_source
    assert 'trace["status"] == "exact_mpc_trace_expansion_built"' in side_source
    assert 'trace["full_trace_rows"]' in side_source
    assert "condensed.trace_rows" in side_source
    assert "condensed.active_rows" in side_source
    for threshold in ("1.0e-10", "1.0e-8", "1.0e-30"):
        assert threshold in side_source

    recovery_source = inspect.getsource(runner.recover_frozen_m10)
    positions = [
        recovery_source.index("pre_cleanup = collective_heap_cleanup(comm)"),
        recovery_source.index('"bottom", setup, linear'),
        recovery_source.index("bottom_cleanup = collective_heap_cleanup(comm)"),
        recovery_source.index('"top", setup, linear'),
        recovery_source.index("top_cleanup = collective_heap_cleanup(comm)"),
    ]
    assert positions == sorted(positions)
    assert 'linear.release.get("pass") is not True' in recovery_source
    assert 'bottom_report["external_q"]["pass"]' in recovery_source
    assert 'top_report["external_q"]["pass"]' in recovery_source
    assert "recovery_pass=True" in recovery_source

    runner_source = inspect.getsource(runner.run_frozen_m10)
    for symbol in (
        "build_frozen_m10_setup",
        "solve_frozen_m10_linear",
        "recover_frozen_m10",
        "run_frozen_m10_physics",
        "release_frozen_m10_objects",
        "build_frozen_m10_online_record",
    ):
        assert symbol in runner_source
    assert "incomplete" not in runner_source.lower()


def test_physics_stage_has_bounded_grid_and_side_ordered_canonical_contract() -> None:
    source = inspect.getsource(runner.run_frozen_m10_physics)
    for symbol in (
        "evaluate_hybrid_augmented_solution",
        "ModalFieldReconstructor",
        "interface_field_continuity",
        "hybrid_volume_absorption",
        "_write_frozen_m10_grid_payload",
        "_write_canonical_manifest_exports",
        "collective_heap_cleanup",
    ):
        assert symbol in source
    assert "auxiliary_override=(recovery.bottom_q, recovery.top_q)" in source
    assert "order_audit=order_audit" in source
    assert "selected_shape = (5, 20, 40, 3)" in source
    assert "<= 5.0e-3" in source
    assert "<= 1.0e-8" in source
    assert "<= 1.0e-5" in source
    assert 'all(role["pass"] is True for role in export["roles"].values())' in source

    tree = ast.parse(source)
    expected_calls = {
        "evaluate_hybrid_augmented_solution": 1,
        "ModalFieldReconstructor": 1,
        "interface_field_continuity": 1,
        "hybrid_volume_absorption": 1,
        "_write_frozen_m10_grid_payload": 1,
        "_write_canonical_manifest_exports": 2,
    }
    for name, expected in expected_calls.items():
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        assert len(calls) == expected

    calls_by_name = {
        name: next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        for name in (
            "evaluate_hybrid_augmented_solution",
            "interface_field_continuity",
            "hybrid_volume_absorption",
        )
    }
    assert isinstance(
        calls_by_name["evaluate_hybrid_augmented_solution"].args[4], ast.Name
    )
    assert calls_by_name["evaluate_hybrid_augmented_solution"].args[4].id == "solution"
    for name in ("interface_field_continuity", "hybrid_volume_absorption"):
        call = calls_by_name[name]
        assert isinstance(call.args[3], ast.Attribute)
        assert isinstance(call.args[4], ast.Attribute)
        assert isinstance(call.args[3].value, ast.Name)
        assert isinstance(call.args[4].value, ast.Name)
        assert (call.args[3].value.id, call.args[3].attr) == (
            "recovery",
            "bottom_physical",
        )
        assert (call.args[4].value.id, call.args[4].attr) == (
            "recovery",
            "top_physical",
        )

    cleanup_order = [
        source.index("del arrays"),
        source.index("del reconstructor"),
        source.index("del interface_samples"),
        source.index("del selected_planes"),
        source.index("del validation"),
        source.index("pre_canonical_cleanup = collective_heap_cleanup(comm)"),
        source.index("bottom_export = _write_canonical_manifest_exports"),
        source.index("bottom_cleanup = collective_heap_cleanup(comm)"),
        source.index("top_export = _write_canonical_manifest_exports"),
        source.index("del canonical_solution"),
        source.index("top_cleanup = collective_heap_cleanup(comm)"),
    ]
    assert cleanup_order == sorted(cleanup_order)

    payload_source = inspect.getsource(runner._write_frozen_m10_grid_payload)
    for key in (
        '"x_nm"',
        '"y_nm"',
        '"z_nm"',
        '"E_V_per_m"',
        '"H_A_per_m"',
        '"modal_amplitudes"',
        '"bottom_q"',
        '"top_q"',
    ):
        assert key in source
    assert "np.savez(path, **arrays)" in payload_source
    assert "_array_descriptor(value)" in payload_source
    assert "expected_keys" in payload_source
    assert "expected_shapes" in payload_source
    assert "np.all(np.isfinite(value))" in payload_source

    carrier_source = inspect.getsource(runner.FrozenM10Physics)
    assert "selected_planes" not in carrier_source
    assert "reconstructor" not in carrier_source
    formal_source = inspect.getsource(runner.run_frozen_m10)
    assert "build_frozen_m10_setup" in formal_source
    assert "solve_frozen_m10_linear" in formal_source
    assert "recover_frozen_m10" in formal_source
    assert "run_frozen_m10_physics" in formal_source
    assert "release_frozen_m10_objects" in formal_source


def _synthetic_online_record(iterations: int, *, error: str | None = None) -> dict:
    residuals = {
        "reported_relative_residual": 4.0e-9,
        "global_true_relative_residual": 4.0e-9,
        "bottom_true_relative_residual": 4.0e-9,
        "top_true_relative_residual": 4.0e-9,
        "modal_true_relative_residual": 4.0e-9,
    }
    result = SimpleNamespace(
        converged_reason=2,
        iterations=iterations,
        history=[{"iteration": iterations, "multimetric_reason": 2}],
        history_evaluation_count=1,
        postsolve_evaluation_count=1,
        postsolve_audit={**residuals, "pass": True},
        inventory={},
        timing={},
    )
    linear = SimpleNamespace(
        result=result,
        linear_pass=True,
        release={"pass": True},
        inventory={},
        timings={},
    )
    recovery = SimpleNamespace(
        recovery_pass=True,
        reports={},
        timings={},
    )
    physics = SimpleNamespace(
        port_power={},
        traction={},
        interface_continuity={},
        absorption={},
        external_orders=[],
        order_audit={"pass": True},
        energy={},
        own_grid={},
        canonical={},
        cleanup={},
        timings={},
        own_physics_pass=True,
        canonical_pass=True,
        physics_pass=True,
    )
    return runner.build_frozen_m10_online_record(
        case_label="task037b_m10_synthetic",
        source_before={"commit_sha": HEX40, "branch": "test"},
        source_after={
            "clean": True,
            "matches_verified_clean_sha": True,
        },
        authority_bindings={},
        lifecycle={"pass": True, "observed": list(runner.M10_LIFECYCLE_ORDER)},
        linear=linear,
        recovery=recovery,
        physics=physics,
        final_release={"pass": True},
        error=error,
    )


def test_online_record_numerical_and_performance_boundaries() -> None:
    passing = _synthetic_online_record(792)
    assert passing["qualification"]["numerical_pass"] is True
    assert passing["integration_performance_pass"] is True
    assert passing["online_pass"] is True
    assert passing["status"] == "online_candidate_pass_awaiting_offline_checker"
    assert all(
        value == "not_run_offline_checker"
        for value in passing["offline_comparisons"].values()
    )

    slow = _synthetic_online_record(901)
    assert slow["qualification"]["numerical_pass"] is True
    assert slow["qualification"]["integration_performance_pass"] is False
    assert slow["online_pass"] is False

    divergent = _synthetic_online_record(1001)
    assert divergent["qualification"]["numerical_pass"] is False
    assert divergent["online_pass"] is False


def test_online_record_error_is_always_fail_closed() -> None:
    record = _synthetic_online_record(792, error="late release failure")
    assert record["qualification"]["error_free"] is False
    assert record["online_pass"] is False
    assert record["status"] == "failed"


def test_final_release_is_ordered_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Fake:
        def __init__(self) -> None:
            self._destroyed = False
            self.calls = 0

        def destroy(self) -> None:
            self.calls += 1
            self._destroyed = True

    setup = SimpleNamespace(
        _final_release_done=False,
        _final_release_state={},
        coupling=Fake(),
        bottom=Fake(),
        top=Fake(),
        positive=Fake(),
        negative=Fake(),
    )
    recovery = Fake()
    monkeypatch.setattr(
        runner,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )
    first = runner.release_frozen_m10_objects(setup, recovery, None)
    second = runner.release_frozen_m10_objects(setup, recovery, None)
    assert first["order"] == [
        "recovery",
        "coupling",
        "bottom",
        "top",
        "positive",
        "negative",
    ]
    assert first["pass"] is True
    assert second["pass"] is True
    assert all(
        item.calls == 1
        for item in (
            recovery,
            setup.coupling,
            setup.bottom,
            setup.top,
            setup.positive,
            setup.negative,
        )
    )


def test_final_release_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def __init__(self) -> None:
            self._destroyed = False
            self.calls = 0

        def destroy(self) -> None:
            self.calls += 1
            self._destroyed = True

    setup = SimpleNamespace(
        _final_release_done=False,
        _final_release_state={},
        coupling=Fake(),
        bottom=Fake(),
        top=Fake(),
        positive=Fake(),
        negative=Fake(),
    )
    recovery = Fake()
    monkeypatch.setattr(
        runner,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": False},
    )
    first = runner.release_frozen_m10_objects(setup, recovery, None)
    second = runner.release_frozen_m10_objects(setup, recovery, None)
    assert first["pass"] is False
    assert second["pass"] is False
    assert setup._final_release_done is True
    assert recovery.calls == 1


def test_formal_runner_call_order_and_single_stage_helpers() -> None:
    source = inspect.getsource(runner.run_frozen_m10)
    positions = [
        source.index('lifecycle.record("setup")'),
        source.index("build_frozen_m10_setup"),
        source.index('lifecycle.record("solve")'),
        source.index("solve_frozen_m10_linear"),
        source.index('lifecycle.record("retained_solution_postsolve")'),
        source.index("recover_frozen_m10"),
        source.index("run_frozen_m10_physics"),
        source.index("release_frozen_m10_objects"),
        source.index('lifecycle.record("record")'),
    ]
    assert positions == sorted(positions)
    tree = ast.parse(source)
    for name in (
        "build_frozen_m10_setup",
        "solve_frozen_m10_linear",
        "recover_frozen_m10",
        "run_frozen_m10_physics",
        "release_frozen_m10_objects",
        "build_frozen_m10_online_record",
    ):
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        assert len(calls) == 1
    for stage in runner.M10_LIFECYCLE_ORDER[3:-1]:
        assert stage in inspect.getsource(
            runner.recover_frozen_m10
        ) or stage in inspect.getsource(runner.run_frozen_m10_physics)
