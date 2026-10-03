"""Bounded worker/runtime tests for the exact Task40 Review V5 clock."""

import json

import pytest

from src.geometry.task40_nonseparable_plan import (
    TASK40_COMPARISON_GROUP,
    TASK40_GX560_RUN_ID,
    TASK40_GX784_RUN_ID,
    TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
)
from src.io.physical_intermediate_profile import (
    TASK40_0P7NM_PROFILE,
    TASK40_REFERENCE_METRIC_PROFILE,
    profile_facts,
)
from src.runners import workflow_timebase
from src.runners.physical_p4_schur_v14 import (
    _V14Runtime,
    _v14_conditional_time_stop_decision,
)


class _StopBeforeFiniteElementWork(RuntimeError):
    """Test sentinel used immediately after the real worker policy gate."""


def _payload(run_id, timeout_seconds, profile=TASK40_REFERENCE_METRIC_PROFILE):
    return {
        "run_id": run_id,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "method": {"kind": "full3d_iterative"},
        "execution": {
            "timeout_seconds": timeout_seconds,
            "require_zero_swap": True,
        },
        "solver": {
            "preconditioner": profile,
            "stage": "Q4_ORIGINAL",
            "coarse_degree": 4,
            "numeric_cache_mode": "build",
        },
        "derived": {
            "physical_intermediate_profile": profile_facts(
                profile
            )
        },
    }


def _run_bounded_worker(
    tmp_path, monkeypatch, *, run_id, timeout_seconds, policy,
    profile=TASK40_REFERENCE_METRIC_PROFILE,
):
    now = [0.0]

    def clock_sample():
        return {
            "monotonic": now[0],
            "boottime": now[0],
            "utc_ns": int(now[0] * 1.0e9),
        }

    monkeypatch.setattr(workflow_timebase, "clock_sample", clock_sample)
    for name in (
        "PHYSICAL_WATCHDOG_MEMORY_POLICY",
        "PHYSICAL_WATCHDOG_PSS_POLICY",
        "PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES",
        "PHYSICAL_WATCHDOG_PARENT_PID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PHYSICAL_TIMEBASE_GUARD", "1")
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_SHARED_LEDGER_PATH", str(tmp_path / "ledger.json")
    )
    monkeypatch.setenv("PHYSICAL_WATCHDOG_SHARED_ATTEMPT_INDEX", "0")
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_PHASE_PATH", str(tmp_path / "workflow_phase.json")
    )
    ledger_seconds = (
        TASK40_GX784_WORKFLOW_BUDGET_SECONDS
        if run_id == TASK40_GX784_RUN_ID
        else 43200.0
    )
    ledger = {
        "batch_identity": run_id,
        "total_budget_seconds": ledger_seconds,
        "elapsed_seconds": 0.0,
        "stages": {
            "Q4_ORIGINAL": {
                "active_attempt": 0,
                "attempts": [
                    {
                        "source_sha": "s" * 40,
                        "status": "RESERVED",
                        "workflow_clock_start": clock_sample(),
                        "reserved_seconds": ledger_seconds,
                        "time_policy": policy,
                    }
                ],
            }
        },
    }
    (tmp_path / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    runtime_instances = []
    original_contracts = []
    preflight_labels = []

    def make_runtime(*args, **kwargs):
        original_contracts.append(args[2])
        runtime = _V14Runtime(*args, **kwargs)
        runtime_instances.append(runtime)
        return runtime

    def bounded_sample(runtime, label=None, *, enforce=True):
        if label is not None:
            preflight_labels.append(str(label))
        if label == "task40q4_preflight":
            raise _StopBeforeFiniteElementWork("bounded stop after policy gate")
        return {}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as worker
    from src.runners import physical_p4_schur_v14 as v14

    monkeypatch.setattr(v14, "_V14Runtime", make_runtime)
    monkeypatch.setattr(_V14Runtime, "sample", bounded_sample)
    monkeypatch.setattr(v14, "_abi_facts", lambda: {"fixture": "no_numeric_work"})
    monkeypatch.setattr(v14, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        v14,
        "_v14_known_preallocation_gate",
        lambda *_args, **_kwargs: pytest.fail("must stop before the allocation gate"),
    )
    monkeypatch.setattr(
        "src.io.input_validation.simulation_config_3d_from_normalized",
        lambda *_args, **_kwargs: pytest.fail("must stop before FE configuration"),
    )
    result = worker._run_physical_dual_cell_condensed_lowmem(
        _payload(run_id, timeout_seconds, profile),
        tmp_path,
        source_sha="s" * 40,
        profile_identity=profile,
        coarse_degree=4,
        allowed_stages=("Q4_ORIGINAL",),
        batch_identity=run_id,
        evidence_prefix="task40q4",
        summary_schema="task40extra.nonseparable-0p7nm.p6q4.worker-summary.v1",
        summary_filename="worker_summary.json",
        derive_live_space_identity=True,
        restore_summary_schema=True,
    )
    return result, runtime_instances, original_contracts, preflight_labels, now


def test_gx784_worker_installs_full_enforced_clock_and_runtime_gates(
    tmp_path, monkeypatch
):
    result, runtimes, original_contracts, labels, now = _run_bounded_worker(
        tmp_path,
        monkeypatch,
        run_id=TASK40_GX784_RUN_ID,
        timeout_seconds=TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
        policy="enforce",
    )

    assert labels == ["task40q4_preflight", "task40q4_post_cleanup"]
    assert result["summary"]["error"]["type"] == "_StopBeforeFiniteElementWork"
    assert result["summary"]["time_policy"] == "enforce"
    authority = result["summary"]["time_budget_authority"]
    assert authority["authorization"] == "task40_review_v5_exact_gx784"
    assert authority["hard_limit_seconds"] == 172800.0

    runtime = runtimes[0]
    assert runtime.contract is not original_contracts[0]
    resources = runtime.contract["resources"]
    assert resources["stage_budgets"]["Q4_ORIGINAL"] == {
        "workflow_seconds": 172800.0,
        "solve_seconds": 172800.0,
    }
    assert resources["pc_soft_seconds"] == 172800.0
    assert resources["pc_hard_seconds"] == 172800.0
    assert resources["time_policy"] == "enforce"
    assert resources["require_observe_only"] is False
    original_resources = original_contracts[0]["resources"]
    assert original_resources["stage_budgets"]["Q4_ORIGINAL"] == {
        "workflow_seconds": 43200,
        "solve_seconds": 43200,
    }
    assert original_resources["pc_soft_seconds"] == 25
    assert original_resources["pc_hard_seconds"] == 30
    assert original_resources["time_policy"] == "observe_only"
    assert original_resources["require_observe_only"] is True

    # The old 25/30-second reference PC values would have stopped this real
    # Runtime branch.  A 31-second PC remains admissible under the new total
    # workflow cap, while the actual Q4 stop decision still fires at 172800.
    runtime.begin_outer_solve()
    runtime.begin_pc(1)
    now[0] = 31.0
    pc_facts = runtime.finish_pc()
    assert pc_facts["soft_limit_seconds"] == 172800.0
    assert pc_facts["hard_limit_seconds"] == 172800.0
    assert not pc_facts["soft_stop_requested"]
    assert not pc_facts["hard_limit_exceeded"]
    assert not runtime.pc_soft_stop_requested
    runtime.finish_outer_solve()

    below_limit = _v14_conditional_time_stop_decision(
        solve_elapsed=31.0,
        workflow_elapsed=172799.0,
        solve_limit=172800.0,
        workflow_limit=172800.0,
        time_policy="enforce",
    )
    at_limit = _v14_conditional_time_stop_decision(
        solve_elapsed=31.0,
        workflow_elapsed=172800.0,
        solve_limit=172800.0,
        workflow_limit=172800.0,
        time_policy="enforce",
    )
    assert below_limit["reason"] is None
    assert below_limit["workflow_time_gate"]["passed"] is True
    assert at_limit["reason"] == "workflow_budget_reached"
    assert at_limit["workflow_time_gate"]["exceeded"] is True


def test_gx560_worker_retains_legacy_observe_only_clock(tmp_path, monkeypatch):
    result, runtimes, _original_contracts, labels, _now = _run_bounded_worker(
        tmp_path,
        monkeypatch,
        run_id=TASK40_GX560_RUN_ID,
        timeout_seconds=43200,
        policy="observe_only",
    )

    assert labels == ["task40q4_preflight", "task40q4_post_cleanup"]
    assert result["summary"]["time_policy"] == "observe_only"
    assert result["summary"]["time_budget_authority"]["authorization"] == (
        "historical_v20_observe_only"
    )
    resources = runtimes[0].contract["resources"]
    assert resources["stage_budgets"]["Q4_ORIGINAL"] == {
        "workflow_seconds": 43200,
        "solve_seconds": 43200,
    }
    assert resources["pc_soft_seconds"] == 25
    assert resources["pc_hard_seconds"] == 30
    assert resources["require_observe_only"] is True


@pytest.mark.parametrize(
    ("run_id", "timeout_seconds", "policy", "message", "profile"),
    [
        (
            TASK40_GX784_RUN_ID,
            43200,
            "enforce",
            "172800-second input budget",
            TASK40_REFERENCE_METRIC_PROFILE,
        ),
        (
            TASK40_GX784_RUN_ID,
            TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
            "observe_only",
            "parent-enforced time policy",
            TASK40_REFERENCE_METRIC_PROFILE,
        ),
        (
            "task40extra_0p7nm_nonseparable_wrong_v5_v1",
            TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
            "enforce",
            "reserved for the exact Task40 Review V5 Gx784 input",
            TASK40_REFERENCE_METRIC_PROFILE,
        ),
        (
            TASK40_GX784_RUN_ID,
            TASK40_GX784_WORKFLOW_BUDGET_SECONDS,
            "enforce",
            "exact profile, Q4 identity",
            TASK40_0P7NM_PROFILE,
        ),
    ],
)
def test_v20_worker_rejects_wrong_gx784_run_id_budget_or_policy(
    tmp_path, monkeypatch, run_id, timeout_seconds, policy, message, profile
):
    result, _runtimes, _original_contracts, labels, _now = _run_bounded_worker(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
        policy=policy,
        profile=profile,
    )

    assert "task40q4_preflight" not in labels
    assert message in result["summary"]["error"]["message"]
