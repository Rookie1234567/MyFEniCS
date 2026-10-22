from __future__ import annotations

from benchmarks.subreaper_watchdog import (
    _legacy_resource_stop_reason,
    memory_envelope,
)
from benchmarks.task43_hp_adaptivity.profile import (
    TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE,
    task43_watchdog_resource_gate_from_environment,
)
from src.common.config_3d import (
    LEGACY_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
    TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY,
    variable_p_active_fe_dof_gate_limit,
)
from src.io.native_capacity_profile import native_profile_facts
from src.solvers.dtn_port_3d import _dof_row_semantics

_GIB = 1024**3


def test_task43_resource_profile_is_explicit_and_not_a_legacy_alias():
    facts = native_profile_facts(TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE)
    resources = facts["resources"]
    assert facts["identity"] == TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    assert resources["absolute_cap_bytes"] == 192 * _GIB
    assert resources["planning_cap_bytes"] == 192 * _GIB
    assert resources["reserve_min_bytes"] == 64 * _GIB
    assert resources["reserve_fraction"] == 0.15
    assert resources["resource_stop_policy"] == "legacy"
    assert resources["require_zero_swap"] is True
    assert "Task43 only" in resources["research_scope"]
    assert (
        variable_p_active_fe_dof_gate_limit(
            LEGACY_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY
        )
        == 90_000
    )
    assert (
        variable_p_active_fe_dof_gate_limit(
            TASK43_VARIABLE_P_ACTIVE_FE_DOF_GATE_POLICY
        )
        is None
    )


def test_task43_memory_envelope_uses_effective_reserve_and_cap(monkeypatch):
    import benchmarks.subreaper_watchdog as watchdog

    monkeypatch.setenv(
        "PHYSICAL_NATIVE_CAPACITY", TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    )
    monkeypatch.delenv("PHYSICAL_NATIVE_NODE_CAP_BYTES", raising=False)
    monkeypatch.setattr(
        watchdog,
        "wsl_memory_snapshot",
        lambda: {
            "mem_total_bytes": 512 * _GIB,
            "mem_available_bytes": 200 * _GIB,
        },
    )
    monkeypatch.setattr(watchdog, "current_cgroup_path", lambda: None)

    envelope = memory_envelope()

    assert envelope["resource_profile_identity"] == TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    assert envelope["effective_total_bytes"] == 512 * _GIB
    assert envelope["reserve_bytes"] == int(0.15 * 512 * _GIB)
    assert envelope["launch_cap_bytes"] == 200 * _GIB - envelope["reserve_bytes"]
    assert envelope["planning_cap_bytes"] == envelope["launch_cap_bytes"]


def test_task43_watchdog_worker_marker_requires_profile_caps_and_zero_swap():
    environment = {
        "PHYSICAL_WATCHDOG_RESOURCE_PROFILE_IDENTITY": (
            TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
        ),
        "PHYSICAL_WATCHDOG_RESOURCE_STOP_POLICY": "legacy",
        "PHYSICAL_WATCHDOG_REQUIRE_ZERO_SWAP": "1",
        "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES": str(192 * _GIB),
        "PHYSICAL_WATCHDOG_RESERVE_BYTES": str(64 * _GIB),
        "PHYSICAL_WATCHDOG_PLANNING_CAP_BYTES": str(180 * _GIB),
    }
    result = task43_watchdog_resource_gate_from_environment(environment)
    assert result["status"] == "verified"
    assert result["launch_cap_bytes"] == 192 * _GIB
    assert result["planning_cap_bytes"] == 180 * _GIB

    environment["PHYSICAL_WATCHDOG_RESOURCE_PROFILE_IDENTITY"] = "task40"
    try:
        task43_watchdog_resource_gate_from_environment(environment)
    except RuntimeError as exc:
        assert "not bound to the Task43 resource profile" in str(exc)
    else:
        raise AssertionError("a non-Task43 watchdog identity was accepted")


def test_task43_supervise_exports_verified_worker_markers_and_cleans_tree(tmp_path):
    import json
    import os
    import subprocess
    import sys

    worker_record = tmp_path / "worker-gate.json"
    run_directory = tmp_path / "watchdog-run"
    worker = (
        "import json,os; from pathlib import Path; "
        "from benchmarks.task43_hp_adaptivity.profile import "
        "task43_watchdog_resource_gate_from_environment; "
        "gate=task43_watchdog_resource_gate_from_environment(); "
        "payload={'gate':gate, "
        "'native_identity':os.environ.get('PHYSICAL_NATIVE_CAPACITY')}; "
        f"Path({str(worker_record)!r}).write_text("
        "json.dumps(payload, sort_keys=True, allow_nan=False))"
    )
    monitor = (
        "import json,sys; from pathlib import Path; "
        "import benchmarks.subreaper_watchdog as watchdog; "
        f"summary=watchdog.supervise([sys.executable,'-c',{worker!r}], "
        f"Path({str(run_directory)!r}), wall_seconds=15, interval=0.1); "
        "print(json.dumps(summary, allow_nan=False))"
    )
    environment = os.environ.copy()
    environment["PHYSICAL_NATIVE_CAPACITY"] = TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    environment.pop("PHYSICAL_WATCHDOG_PSS_POLICY", None)
    process = subprocess.run(
        [sys.executable, "-c", monitor],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads(process.stdout.splitlines()[-1])
    worker_result = json.loads(worker_record.read_text())
    envelope = summary["launch_memory_envelope"]
    gate = worker_result["gate"]

    assert summary["classification"] == "COMPLETED"
    assert summary["descendants_cleared"] is True
    assert summary["remaining_child_pids"] == []
    assert summary["native_capacity_profile_identity"] == (
        TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    )
    assert worker_result["native_identity"] == TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE
    assert gate["status"] == "verified"
    assert gate["launch_cap_bytes"] == envelope["launch_cap_bytes"]
    assert gate["effective_reserve_bytes"] == envelope["reserve_bytes"]
    assert gate["planning_cap_bytes"] == envelope["planning_cap_bytes"]
    assert summary["native_capacity_resource_facts"]["absolute_cap_bytes"] == (
        192 * _GIB
    )


def test_h100_anchor_preflight_records_verified_task43_watchdog_gate(monkeypatch):
    from mpi4py import MPI

    from benchmarks.task43_hp_adaptivity.h100_anchor import _check_environment

    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
    monkeypatch.setenv("MKL_NUM_THREADS", "1")
    monkeypatch.setenv("NUMEXPR_NUM_THREADS", "1")
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_RESOURCE_PROFILE_IDENTITY",
        TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE,
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_RESOURCE_STOP_POLICY", "legacy")
    monkeypatch.setenv("PHYSICAL_WATCHDOG_REQUIRE_ZERO_SWAP", "1")
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", str(192 * _GIB)
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_RESERVE_BYTES", str(64 * _GIB)
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_PLANNING_CAP_BYTES", str(180 * _GIB)
    )

    environment = _check_environment(MPI.COMM_SELF)

    assert environment["task43_watchdog_resource_gate"] == {
        "status": "verified",
        "resource_profile_identity": TASK43_HP_ADAPTIVITY_RESOURCE_PROFILE,
        "resource_stop_policy": "legacy",
        "launch_cap_bytes": 192 * _GIB,
        "effective_reserve_bytes": 64 * _GIB,
        "planning_cap_bytes": 180 * _GIB,
        "zero_task_tree_swap_required": True,
    }


def test_task43_legacy_runtime_gate_stops_for_each_requested_hard_limit():
    baseline = {
        "process_tree_rss_bytes": 1,
        "launch_cap_bytes": 10,
        "effective_available_bytes": 100,
        "reserve_bytes": 64,
        "process_tree_swap_bytes": 0,
    }
    assert _legacy_resource_stop_reason(**baseline) is None
    assert _legacy_resource_stop_reason(
        **{**baseline, "process_tree_rss_bytes": 10}
    ) == "RESOURCE_CONTROLLED_STOP"
    assert _legacy_resource_stop_reason(
        **{**baseline, "effective_available_bytes": 63}
    ) == "RESOURCE_CONTROLLED_STOP"
    assert _legacy_resource_stop_reason(
        **{**baseline, "process_tree_swap_bytes": 1}
    ) == "RESOURCE_CONTROLLED_STOP"


def test_independent_dof_count_is_optional_for_legacy_rows_and_explicit_for_task43():
    legacy = _dof_row_semantics(
        active_exact_sequence_fe_dofs=80,
        storage_carrier_fe_dofs=120,
        independent_trace_rows=50,
        augmented_rows=62,
        auxiliary_rows=12,
    )
    assert legacy["num_independent_active_fe_dofs"] is None

    task43 = _dof_row_semantics(
        active_exact_sequence_fe_dofs=80,
        storage_carrier_fe_dofs=120,
        independent_trace_rows=50,
        independent_active_fe_dofs=65,
        augmented_rows=62,
        auxiliary_rows=12,
    )
    assert task43["num_independent_active_fe_dofs"] == 65
