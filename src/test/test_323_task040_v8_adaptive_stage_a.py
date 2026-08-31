"""Pure contracts for the opt-in adaptive Stage-A benchmark route."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from benchmarks import task040_level_a as level_a
from benchmarks import task040_level_a_watchdog as watchdog


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
    total = watchdog._v8_adaptive_active_stage_timeout(
        "v8_adaptive_checkpoint",
        stage_elapsed_seconds=1.0,
        total_elapsed_seconds=10801.0,
    )
    assert total["timed_out"] is True
    assert total["kind"] == "total"
    one_apply = watchdog._v8_adaptive_active_stage_timeout(
        "v8_adaptive_external_one_apply_begin",
        stage_elapsed_seconds=1201.0,
        total_elapsed_seconds=1.0,
    )
    assert one_apply["timed_out"] is True
    assert one_apply["kind"] == "one_apply"
