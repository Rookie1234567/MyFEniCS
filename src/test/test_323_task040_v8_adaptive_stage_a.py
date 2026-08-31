"""Pure contracts for the opt-in adaptive Stage-A benchmark route."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import task040_level_a as level_a
from benchmarks import task040_level_a_watchdog as watchdog
from benchmarks import task040_v6_2_interface_schur as interface_schur
from src.solvers import hybrid_adaptive_impedance_screen as screen
from src.solvers import hybrid_maxwell_harmonic_coarse as harmonic_coarse


def _route_values(tmp_path: Path) -> dict[str, object]:
    input_path = tmp_path / "task040.dat"
    input_path.write_text("synthetic route input\n", encoding="utf-8")
    spool = tmp_path / "bare_f_authority"
    spool.mkdir()
    return {
        "input_path": input_path,
        "exact_spool_root": spool,
        "run_directory": tmp_path / "run",
        "source_sha": "a" * 40,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "v8_adaptive_schwarz_only": True,
        "v8_full_spectrum_only": False,
        "v7_moving_pml_full_state": False,
        "v7_scale_normalized_identity": False,
        "v6_2_interface_schur": False,
        "v5_route_c": False,
        "packet_producer": False,
        "watchdog_enabled": True,
        "bottom_route_only": True,
    }


def _call_builder(builder, values):
    signature = inspect.signature(builder)
    kwargs = {
        name: values[name]
        for name in signature.parameters
        if name in values
    }
    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty and name not in kwargs
    ]
    if missing:
        raise AssertionError(f"route fixture lacks required plan fields: {missing}")
    return builder(**kwargs)


def test_v8_adaptive_stage_a_route_and_marker_contract(tmp_path):
    values = _route_values(tmp_path)
    plan = _call_builder(level_a.build_task040_level_a_plan, values)
    assert plan["v8_adaptive_schwarz_only"] is True
    assert plan["fixed_configuration"]["gamma_canonical_interface"] is False
    assert plan["source_order"] == ["external_dtn_coupling"]
    assert plan["mandatory_checkpoints"] == ["one_apply"]
    assert plan["conditional_checkpoints"] == []
    assert plan["preferred_memory_bytes"] == 35 * 2**30
    assert plan["absolute_terminate_memory_bytes"] == 45 * 2**30
    assert plan["timeout_seconds"] == 10800

    with pytest.raises(ValueError):
        _call_builder(
            level_a.build_task040_level_a_plan,
            {**values, "v8_full_spectrum_only": True},
        )

    watchdog_plan = _call_builder(
        watchdog.build_task040_level_a_watchdog_plan,
        values,
    )
    worker_argv = watchdog._worker_command(watchdog_plan)
    assert "--v8-adaptive-schwarz-only" in worker_argv
    assert "--v8-full-spectrum-only" not in worker_argv
    assert "--v7-moving-pml-full-state" not in worker_argv
    assert "--v7-scale-normalized-identity" not in worker_argv
    assert watchdog_plan["watchdog"]["preferred_memory_bytes"] == 35 * 2**30
    assert watchdog_plan["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert watchdog_plan["watchdog"]["swap_limit_bytes"] == 0
    assert watchdog_plan["watchdog"]["timeout_seconds"] == 10800

    marker_events = (
        "v8_adaptive_preflight",
        "v8_adaptive_system_ready",
        "v8_adaptive_factor_ready",
        "v8_adaptive_external_one_apply_begin",
        "v8_adaptive_external_one_apply_end",
        "v8_adaptive_checkpoint",
        "v8_adaptive_cleanup_complete",
    )
    assert plan["marker_sequence"] == list(marker_events)
    b1_begin = watchdog._v8_adaptive_active_stage_timeout(
        "v8_adaptive_stage_b1_begin",
        stage_elapsed_seconds=3601.0,
        total_elapsed_seconds=10799.0,
    )
    assert b1_begin["timed_out"] is False
    assert b1_begin["kind"] is None
    total = watchdog._v8_adaptive_active_stage_timeout(
        "v8_adaptive_stage_b1_begin",
        stage_elapsed_seconds=1.0,
        total_elapsed_seconds=10801.0,
    )
    assert total["timed_out"] is True
    assert total["kind"] == "total"
    assert "v8_adaptive_stage_b1_cleanup_complete" in (
        watchdog._TERMINAL_CLEANUP_STAGES
    )
    assert "v8_adaptive_stage_b1_failure" not in (
        watchdog._TERMINAL_CLEANUP_STAGES
    )
    one_apply = watchdog._v8_adaptive_active_stage_timeout(
        "v8_adaptive_external_one_apply_begin",
        stage_elapsed_seconds=1201.0,
        total_elapsed_seconds=1.0,
    )
    assert one_apply["timed_out"] is True
    assert one_apply["kind"] == "one_apply"

    b1_values = {
        **values,
        "v8_adaptive_schwarz_only": False,
        "v8_adaptive_stage_b1_only": True,
    }
    b1_plan = _call_builder(level_a.build_task040_level_a_plan, b1_values)
    assert b1_plan["schema"] == interface_schur.V8_ADAPTIVE_STAGE_B1_ONLY_SCHEMA
    assert b1_plan["method"] == interface_schur.V8_ADAPTIVE_STAGE_B1_ONLY_METHOD
    assert b1_plan["profile"] == interface_schur.V8_ADAPTIVE_STAGE_B1_ONLY_PROFILE_ID
    assert b1_plan["source_order"] == []
    assert b1_plan["mandatory_checkpoints"] == []
    assert b1_plan["one_apply_target_seconds"] is None
    assert b1_plan["fixed_configuration"]["operation"] == (
        "symbolic_identity_and_memory_preflight_only"
    )
    assert {"P", "P_H", "FP", "Ac", "fgmres"} <= set(
        b1_plan["forbidden"]
    )
    assert b1_plan["marker_sequence"][-1] == (
        "v8_adaptive_stage_b1_cleanup_complete"
    )
    b1_watchdog = _call_builder(
        watchdog.build_task040_level_a_watchdog_plan,
        b1_values,
    )
    b1_argv = watchdog._worker_command(b1_watchdog)
    assert "--v8-adaptive-stage-b1-only" in b1_argv
    assert "--v8-adaptive-schwarz-only" not in b1_argv
    assert "--watchdog-enabled" in b1_argv
    assert "--bottom-route-only" in b1_argv
    assert b1_watchdog["watchdog"]["hard_stop_bytes"] == 45 * 2**30
    assert b1_watchdog["watchdog"]["swap_limit_bytes"] == 0
    assert b1_watchdog["watchdog"]["timeout_seconds"] == 10800
    assert b1_watchdog["watchdog"]["one_apply_target_seconds"] is None
    assert b1_watchdog["watchdog"]["cleanup_stage"] == (
        "v8_adaptive_stage_b1_cleanup_complete"
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        _call_builder(
            level_a.build_task040_level_a_plan,
            {**b1_values, "v8_adaptive_schwarz_only": True},
        )


def test_v8_adaptive_callback_and_scoped_swap_authority():
    seen = []
    marker_state = {}
    sentinel = {"rss_bytes": 7}

    def adaptive_mark(stage, **detail):
        seen.append((stage, detail))
        return sentinel

    callback = interface_schur._v8_adaptive_event_callback_factory(
        adaptive_mark, marker_state
    )
    for event in ("factor_ready", "one_apply_begin", "one_apply_end", "checkpoint"):
        callback(event, {"event": event})
    assert [stage for stage, _ in seen] == [
        "v8_adaptive_factor_ready",
        "v8_adaptive_external_one_apply_begin",
        "v8_adaptive_external_one_apply_end",
        "v8_adaptive_checkpoint",
    ]
    callback("cleanup", {"released": True})
    assert marker_state["screen_cleanup"] == {"released": True}

    def authority(cgroup_swap):
        return {
            "process_tree": {"all_status_readable": False, "swap_bytes": 0},
            "job_cgroup": {
                "readable": True,
                "dedicated_job_cgroup": False,
                "swap_current_bytes": cgroup_swap,
            },
        }

    fallback = watchdog._v8_adaptive_swap_authority_sample(
        authority(0), terminal_excluded=False
    )
    assert fallback["authority_readable"] is True
    assert fallback["fallback_used"] is True
    assert fallback["counted"] is True
    for bad in (None, 1):
        sample = watchdog._v8_adaptive_swap_authority_sample(
            authority(bad), terminal_excluded=False
        )
        assert sample["authority_readable"] is False
        assert sample["fallback_used"] is False
    terminal = watchdog._v8_adaptive_swap_authority_sample(
        authority(0), terminal_excluded=True
    )
    assert terminal["counted"] is False

    seen.clear()
    marker_state.clear()
    mapping = {
        "factor_ready": "v8_adaptive_stage_b1_factor_ready",
        "b1_begin": "v8_adaptive_stage_b1_begin",
        "b1_end": "v8_adaptive_stage_b1_end",
    }
    b1_callback = interface_schur._v8_adaptive_event_callback_factory(
        adaptive_mark, marker_state, mapping
    )
    assert b1_callback("factor_ready", {}) is sentinel
    assert b1_callback("b1_begin", {}) is sentinel
    assert b1_callback("b1_end", {}) is sentinel
    assert [stage for stage, _ in seen] == list(mapping.values())
    b1_callback("cleanup", {"released": True})
    assert list(marker_state) == ["screen_cleanup"]
    assert marker_state["screen_cleanup"] == {"released": True}


def test_v8_adaptive_stage_b1_gate_is_early_and_fail_closed(tmp_path):
    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("contract is scoped to serial and MPI2")
    common = {
        "cfg": None, "profile": None, "comm": MPI.COMM_WORLD,
        "exact_spool_root": tmp_path / "spool", "run_directory": tmp_path / "run",
        "source_sha": "a" * 40, "input_path": tmp_path / "input.dat",
        "input_sha256": "b" * 64, "physical_model_sha256": "c" * 64,
    }
    with pytest.raises(ValueError, match="mutually exclusive"):
        interface_schur.run_v6_2_interface_schur(
            **common,
            v8_adaptive_schwarz_only=True,
            v8_adaptive_stage_b1_only=True,
        )
    result = interface_schur.run_v6_2_interface_schur(
        **common, v8_adaptive_stage_b1_only=True
    )
    assert result["schema"] == interface_schur.V8_ADAPTIVE_STAGE_B1_ONLY_SCHEMA
    assert result["classification"] == "V8_ADAPTIVE_STAGE_B1_NOT_RUN"
    assert result["pass"] is None
    assert result["source_order"] == []


class _FakeB1Owner:
    def __init__(self, action=False):
        self.destroyed = False
        self.diagnostics = {"factor_lifecycle": {"ready": int(action)}}

    def destroy(self):
        self.destroyed = True
        self.diagnostics["factor_lifecycle"] = {"ready": 0}


def _fake_b1_evidence(*_args, **_kwargs):
    return {
        "identity_pass": True,
        "patch_count": 1,
        "selected_modes_per_patch_histogram": {1: 1},
        "selected_mode_count_total": 1,
        "memory_preflight": {
            "allocation_allowed": True,
            "projected_peak_bytes_conservative": 1,
            "route": "exact_preflight",
        },
    }


def test_v8_adaptive_b1_screen_owns_resources_and_syncs_baseline(monkeypatch):
    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("run this fake distributed contract with serial or MPI2")
    created = {"providers": [], "actions": [], "identity": 0}

    def make_builder(kind):
        def build(*_args, **_kwargs):
            owner = _FakeB1Owner(kind == "actions")
            created[kind].append(owner)
            return owner

        return build

    def identity(*_args, **_kwargs):
        created["identity"] += 1
        return _fake_b1_evidence()

    monkeypatch.setattr(
        screen,
        "build_actual_hcurl_cell_tangential_mass_provider",
        make_builder("providers"),
    )
    monkeypatch.setattr(
        screen, "build_adaptive_impedance_schwarz_action", make_builder("actions")
    )
    monkeypatch.setattr(harmonic_coarse, "build_stage_b1_harmonic_identity", identity)
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 1), (PETSc.DECIDE, 1)),
        nnz=1,
        comm=MPI.COMM_WORLD,
    )
    matrix.setUp()
    matrix.assemble()
    try:
        events = []

        def callback(events, swap):
            def emit(event, _detail):
                events.append(event)
                if event == "factor_ready":
                    return {
                        "all_status_readable": True,
                        "pass": True,
                        "rss_bytes": 1,
                        "swap_bytes": swap,
                        "source": "fake-process-tree",
                    }
                return None

            return emit

        base = {
            "function_space": object(),
            "condensed": object(),
            "bare_f": matrix,
            "cell_tags": None,
            "facet_tags": None,
            "external_facet_tag": 7,
            "beta": 1.0,
            "quadrature_degree": 2,
        }
        success = screen.run_adaptive_impedance_stage_b1_preflight(
            **base, event_callback=callback(events, 0)
        )
        assert events == ["factor_ready", "b1_begin", "b1_end", "cleanup"]
        assert success["evidence"]["identity_pass"] is True
        assert success["setup_wall_seconds"] >= 0.0
        assert success["b1_wall_seconds"] >= 0.0
        assert success["bare_f_hash_before"] == success["bare_f_hash_after"]
        assert success["cleanup"]["action_destroyed"] is True
        assert success["cleanup"]["provider_destroyed"] is True
        assert success["cleanup"]["factor_lifecycle_after"] == {"ready": 0}
        assert created["actions"][0].destroyed is True
        assert created["providers"][0].destroyed is True
        assert matrix.getSize() == (1, 1)
        assert created["identity"] == 1

        failure_events = []
        with pytest.raises(RuntimeError, match="resource snapshot"):
            screen.run_adaptive_impedance_stage_b1_preflight(
                **base, event_callback=callback(failure_events, 1)
            )
        assert failure_events == ["factor_ready", "cleanup"]
        assert created["identity"] == 1
        assert created["actions"][-1].destroyed is True
        assert created["providers"][-1].destroyed is True
    finally:
        matrix.destroy()
