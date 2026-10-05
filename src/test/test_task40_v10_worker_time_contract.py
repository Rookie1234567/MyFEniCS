from types import SimpleNamespace

import pytest

from src.geometry.task40_nonseparable_plan import (
    TASK40_B0_CONTROL_RUN_ID,
    TASK40_B0_P4_CONTROL_PROFILE,
    TASK40_COMPARISON_GROUP,
)
from src.runners.physical_dual_cell_condensed_lowmem_v20 import (
    _resolve_v20_worker_time_contract,
)
from src.io.physical_intermediate_profile import (
    TASK40_V10_P6_REFERENCE_PROFILE,
    profile_facts,
)


def _v10_runtime(*, ledger_path=None):
    return SimpleNamespace(
        time_policy="enforce",
        shared_attempt={"time_policy": "enforce", "reserved_seconds": 72000.0},
        shared_budget={
            "schema": "task40extra.review_v10_campaign_worker_view.v1",
            "total_budget_seconds": 86400.0,
            "writer_while_worker_active": "subreaper_watchdog_only",
            "worker_access": "read_only_projection",
        },
        workflow_reserved_seconds=72000.0,
        campaign_context={
            "read_only": True,
            "window_path": "/campaign/window.json",
            "window_sha256": "a" * 64,
            "accounting_path": "/campaign/accounting.jsonl",
        },
        _ledger_path=ledger_path,
        contract={
            "identity": TASK40_B0_P4_CONTROL_PROFILE,
            "scope": "task40_review_v10_b0_full_p4_balh_control",
            "resources": {
                "campaign_closeout_reserve_seconds": 600.0,
                "stage_budgets": {
                    "B0_CONTROL": {
                        "workflow_seconds": 86400.0,
                        "solve_seconds": 86400.0,
                    }
                },
            },
        },
    )


def _v10_payload():
    return {
        "run_id": TASK40_B0_CONTROL_RUN_ID,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "method": {"kind": "full3d_iterative"},
        "execution": {
            "timeout_seconds": 86400,
            "mpi_size": 1,
            "require_zero_swap": True,
        },
        "solver": {
            "preconditioner": TASK40_B0_P4_CONTROL_PROFILE,
            "stage": "B0_CONTROL",
            "ksp_type": "fgmres",
            "restart": 32,
            "max_iterations": 2048,
            "coarse_degree": 4,
            "physical_operator_backend": "isotropic_sum_factorized_n1e_v26",
            "h6_backend_rule": "direct_selected_backend_same_apply_and_power10",
        },
    }


def test_v10_b0_worker_uses_watchdog_owned_campaign_projection_read_only():
    authority = _resolve_v20_worker_time_contract(
        _v10_payload(),
        _v10_runtime(),
        profile=TASK40_B0_P4_CONTROL_PROFILE,
        stage="B0_CONTROL",
    )

    assert authority["authorization"] == (
        "task40_review_v10_b0_p4_watchdog_campaign_projection"
    )
    assert authority["campaign_seconds"] == 86400.0
    assert authority["closeout_reserve_seconds"] == 600.0
    assert authority["worker_accounting_access"] == "read_only_projection"
    resources = profile_facts(TASK40_B0_P4_CONTROL_PROFILE)["resources"]
    assert resources["pc_soft_seconds"] == resources["pc_hard_seconds"] == 86400
    assert resources["pc_limit_policy"] == "fixed_v10_campaign_remaining_at_worker_entry"
    candidate_resources = profile_facts(TASK40_V10_P6_REFERENCE_PROFILE)["resources"]
    assert candidate_resources["pc_soft_seconds"] == candidate_resources["pc_hard_seconds"] == 86400
    assert candidate_resources["pc_limit_policy"] == (
        "fixed_v10_campaign_remaining_at_worker_entry"
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda runtime, payload: setattr(runtime, "_ledger_path", "/old/v14-ledger.json"),
        lambda runtime, payload: payload["solver"].update(coarse_degree=3),
        lambda runtime, payload: runtime.campaign_context.update(read_only=False),
    ],
)
def test_v10_b0_worker_rejects_legacy_ledger_or_changed_campaign_identity(change):
    runtime = _v10_runtime()
    payload = _v10_payload()
    change(runtime, payload)

    with pytest.raises(ValueError, match="exact p4 BAL_H input"):
        _resolve_v20_worker_time_contract(
            payload,
            runtime,
            profile=TASK40_B0_P4_CONTROL_PROFILE,
            stage="B0_CONTROL",
        )
