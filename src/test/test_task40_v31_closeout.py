import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from scripts.task40_v20_service_workflow import (
    _task40_v30_closeout_checker_authorization,
)
from benchmarks.subreaper_watchdog import _validate_campaign_closeout_authorization
from src.io.physical_intermediate_profile import (
    TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    profile_facts,
)
from src.runners.task40_v10_output_checker import (
    _positive_registered_channel_count,
    _verify_v30_all_q_rhs_cost_categories,
    _verify_v31_reference_inverse_product,
    _verify_v31_reference_tiers,
)
from src.runners.task40_v10_campaign import (
    CAMPAIGN_SCHEMA,
    TASK40_V31_CAMPAIGN_SECONDS,
    TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
    FixedCampaignWindow,
    _validate_v31_campaign_registration,
)
from src.runners.task40_v31_contract import (
    V31_ARTIFACT_ROOT_RELATIVE,
    V31_FACTOR_BANK_SCHEMA,
    V31_PROFILE,
    V31_Q_CSR_BINDING_SCHEMA,
    V31_Q_WORKLIST,
    V31_RESOURCES,
    V31_WORKER_BINDING_SCHEMA,
    V31_REVIEW_COMMIT,
    V31_REVIEW_PATH,
    V31_REVIEW_SHA256,
    V31_STAGE_SCOPE,
    require_v31_all_q_route,
    validate_v31_worker_execution_binding,
    v31_launcher_values,
)
from src.solvers.task40_v10_p6_periodic_profile import (
    TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE as V31_PERIODIC_PROFILE,
)
from src.runners.workflow_timebase import CONSERVATIVE_REALTIME


V30_PROFILE = TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
V30_CHANNEL_COUNT = profile_facts(V30_PROFILE)["gates"]["all_original_modes_retained"]
V31_REFERENCE_CASES = (
    "generic_full_independent",
    f"interior_only_all_{V31_PERIODIC_PROFILE.global_interior_rows}",
    "nonzero_all_mode_port_rhs",
    "physical_regular_incident_rhs",
    "mixed_generic_fe_and_all_mode_port_rhs",
    "mixed_interior_fe_and_all_mode_port_rhs",
)


def _v31_reference_tier_fixture() -> dict:
    from src.solvers.augmented_reference_correction import (
        STRICT_REFERENCE_PASS,
        V15_REFERENCE_PC_PASS,
        select_reference_pc_candidate,
    )

    sector_facts = []
    offset = 0
    for twist, count in enumerate(V31_PERIODIC_PROFILE.sector_port_counts):
        sector_facts.append(
            {"twist_index": twist, "mode_indices": list(range(offset, offset + count))}
        )
        offset += count
    state_sha = "a" * 64
    metrics = {
        "eliminated_fe": 0.0,
        "complete_augmented_fe": 0.0,
        "noncancelling_budget": 0.0,
        "alpha_closure": 0.0,
        "q_solve": 0.0,
    }
    frozen = {key: 0.0 for key in metrics if key != "q_solve"}
    candidate = {
        "state_label": "initial",
        "metrics": metrics,
        "frozen_scale_metrics": frozen,
        "structural_gates": {"full_augmented_structure": True},
        "state_sha256": state_sha,
        "raw_facts": {
            "profile_identity": V31_PROFILE,
            "effective_rhs_scale": 1.0,
            "eliminated_fe_residual_norm": 0.0,
            "complete_augmented_fe_residual_norm": 0.0,
            "budget_term_norms": {
                "d_b": 0.0,
                "lifted_sector_errors": [0.0] * V31_PERIODIC_PROFILE.replication_count,
                "d_A": 0.0,
                "B_delta_alpha": 0.0,
            },
            "alpha_closure_residual_norm": 0.0,
            "alpha_closure_original_scale": 1.0,
            "alpha_closure_frozen_scale": 1.0,
            "q_true_residuals": [
                {
                    "q": q,
                    "rhs_norm": 1.0,
                    "true_residual_norm": 0.0,
                    "true_residual_relative": 0.0,
                }
                for q in range(V31_PERIODIC_PROFILE.q_count)
            ],
            "retained_mode_count": V31_PERIODIC_PROFILE.mode_count,
            "native_sector_facts": sector_facts,
            "decomposition_closure_norm": 0.0,
            "decomposition_closure_scale": 1.0,
            "state_sha256": state_sha,
        },
    }
    strict_metrics = {
        "full_equation": 0.0,
        "complete_augmented_fe_equation": 0.0,
        "local_sector_0": 0.0,
        "local_sector_1": 0.0,
        "local_combined": 0.0,
        "alpha_closure": 0.0,
        "q_solve": 0.0,
    }
    strict_frozen = dict(strict_metrics)
    strict_candidate = {
        "metrics": strict_metrics,
        "frozen_scale_metrics": strict_frozen,
        "structural_gates": candidate["structural_gates"],
        "state_sha256": state_sha,
        "state_label": "initial",
    }
    strict_selection = select_reference_pc_candidate([strict_candidate])
    rows = []
    strict_by_case = {}
    v15_by_case = {}
    for name in V31_REFERENCE_CASES:
        row = {
            "name": name,
            "reference_pc_candidate": candidate,
            "reference_pc_metrics": strict_metrics,
            "frozen_scale_metrics": strict_frozen,
            "reference_pc_structural_gates": candidate["structural_gates"],
            "reference_pc_admission": V15_REFERENCE_PC_PASS,
            "v15_reference_passed": True,
            "v15_reference_selected_state_sha256": state_sha,
            "strict_reference_admission": strict_selection["admission"],
            "strict_reference_passed": True,
            "strict_reference_selected_state_sha256": state_sha,
            "selected_state_sha256": state_sha,
        }
        rows.append(row)
        strict_by_case[name] = {
            "admission": STRICT_REFERENCE_PASS,
            "passed": True,
            "selected_state_sha256": state_sha,
        }
        v15_by_case[name] = {
            "admission": V15_REFERENCE_PC_PASS,
            "passed": True,
            "selected_state_sha256": state_sha,
        }
    return {
        "schema": "task40extra.review_v30_reference_inverse_checks.v1",
        "profile": V31_PERIODIC_PROFILE.identity(),
        "case_count": len(rows),
        "required_case_names": list(V31_REFERENCE_CASES),
        "observed_case_names": list(V31_REFERENCE_CASES),
        "cases": rows,
        "strict_reference_passed": True,
        "strict_reference_status_by_case": strict_by_case,
        "v15_reference_passed": True,
        "v15_reference_status_by_case": v15_by_case,
    }


def _v31_zero_rhs_cost_audit() -> dict:
    categories = (
        "pc_initial_rhs_mat_solve_count",
        "pc_augmentation_rhs_mat_solve_count",
        "reference_correction_rhs_mat_solve_count",
        "startup_rhs_mat_solve_count",
        "other_validation_rhs_mat_solve_count",
    )
    q_keys = tuple(str(q) for q in range(V31_PERIODIC_PROFILE.q_count))
    zeros = {category: 0 for category in categories}
    zero_times = {category: 0.0 for category in categories}
    per_q = {category: {q: 0 for q in q_keys} for category in categories}
    per_q_times = {category: {q: 0.0 for q in q_keys} for category in categories}
    return {
        "rhs_business_call_count_by_category": zeros,
        "rhs_business_call_count_by_category_and_q": per_q,
        "rhs_business_parent_seconds_by_category": zero_times,
        "rhs_business_parent_seconds_by_category_and_q": per_q_times,
        "rhs_business_native_seconds_by_category": dict(zero_times),
        "rhs_business_vector_seconds_by_category": dict(zero_times),
        "mat_solve_invoked_count_by_category": dict(zeros),
        "mat_solve_completed_count_by_category": dict(zeros),
        "mat_solve_failed_count_by_category": dict(zeros),
        "rhs_mat_solve_count_by_category": dict(zeros),
        "S_q_business_seconds_by_q": {q: 0.0 for q in q_keys},
        "S_q_business_parent_seconds_total": 0.0,
        "rhs_business_timing_semantics": {
            "categories_are_disjoint": True,
            "timing_is_child_of_worker_pc_parent": True,
        },
    }


def test_registered_large_mode_count_is_accepted_without_changing_checker_default():
    assert V30_CHANNEL_COUNT == 32_060
    assert _positive_registered_channel_count(str(V30_CHANNEL_COUNT)) == 32_060
    with pytest.raises(argparse.ArgumentTypeError, match="positive"):
        _positive_registered_channel_count("0")


def test_v31_checker_recomputes_strict_and_v15_on_same_six_selected_states():
    checks = _v31_reference_tier_fixture()

    result = _verify_v31_reference_tiers(checks, expected_profile=V31_PROFILE)

    assert result["passed"] is True
    assert result["case_count"] == 6
    assert result["strict_reference_passed"] is True
    assert result["v15_reference_passed"] is True
    assert result["same_selected_complete_state_for_both_tiers"] is True

    broken = json.loads(json.dumps(checks))
    broken["cases"][0]["v15_reference_selected_state_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="same selected state"):
        _verify_v31_reference_tiers(broken, expected_profile=V31_PROFILE)


def test_v31_reference_product_checker_rebinds_hash_and_recomputes_all_q_costs(tmp_path):
    source_sha = "b" * 40
    run_id = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
    input_sha = "c" * 64
    checks = _v31_reference_tier_fixture()
    snapshot = {"factor_audit_before_destroy": _v31_zero_rhs_cost_audit()}
    product = {
        "schema": "task40extra.review_v31_reference_inverse_product.v1",
        "source_sha": source_sha,
        "run_id": run_id,
        "scientific_input_sha256": input_sha,
        "reference_audit_snapshot": snapshot,
        "regular_inverse_checks": checks,
    }
    product_path = tmp_path / "v31_reference_inverse_product.json"
    raw = (json.dumps(product, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    product_path.write_bytes(raw)
    receipt = {
        "schema": "task40extra.review_v31_worker_product_receipt.v1",
        "path": product_path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }
    worker_summary = {
        "profile": V31_PROFILE,
        "source_sha": source_sha,
        "run_id": run_id,
        "v31_input_identity": {"scientific_input_sha256": input_sha},
        "reference_audit_snapshot": snapshot,
        "regular_inverse_checks": checks,
        "v31_reference_inverse_product": receipt,
    }

    result = _verify_v31_reference_inverse_product(
        tmp_path,
        worker_summary,
        expected_q_count=V31_PERIODIC_PROFILE.q_count,
        expected_source_sha=source_sha,
        expected_run_id=run_id,
        expected_input_sha256=input_sha,
    )

    assert result["passed"] is True
    assert result["rhs_cost_recheck"]["schema"] == (
        "task40extra.review_v31_all_q_rhs_cost_categories_checker.v1"
    )
    assert result["reference_tier_recheck"]["case_count"] == 6
    bad_summary = {
        **worker_summary,
        "v31_reference_inverse_product": {**receipt, "sha256": "0" * 64},
    }
    with pytest.raises(ValueError, match="hash or byte count"):
        _verify_v31_reference_inverse_product(
            tmp_path,
            bad_summary,
            expected_q_count=V31_PERIODIC_PROFILE.q_count,
            expected_source_sha=source_sha,
            expected_run_id=run_id,
            expected_input_sha256=input_sha,
        )


def test_v31_partial_checker_reports_reference_cost_as_not_run_before_snapshot(
    monkeypatch, tmp_path
):
    from scripts import task40_v20_service_workflow as service
    from scripts import task40_v21_readonly_recheck

    input_path = tmp_path / "input.dat"
    input_path.write_text(
        f'[solver]\npreconditioner = "{V31_PROFILE}"\n'
        "[execution]\ntask40_target_heavy_authorized = false\n",
        encoding="utf-8",
    )
    source_sha = "b" * 40
    input_sha = service._sha256_file(input_path)
    model_sha = "c" * 64
    from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_SHA256
    from src.runners import task40_v31_contract

    selector_path = tmp_path / "q_csr_selector_v31.json"
    selector_path.write_text("{}\n", encoding="utf-8")
    selector_sha = service._sha256_file(selector_path)
    v31_identity = {
        "canonical_input_path": "/canonical/task40.dat",
        "canonical_input_sha256": V30_CANONICAL_INPUT_SHA256,
        "staged_input_path": str(input_path.resolve()),
        "staged_input_sha256": input_sha,
        "scientific_input_sha256": V30_CANONICAL_INPUT_SHA256,
        "source_sha": source_sha,
    }
    output = tmp_path / "numerical"
    output.mkdir()
    partial = {
        "schema": "task40extra.review_v20_partial_result.v2",
        "status": "controlled_stop",
        "outcome": "RESOURCE_CONTROLLED_STOP",
        "run_id": "fixture_v31",
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": model_sha,
        "requested_stop_stage": "full",
        "attempted_stages": ["preflight"],
        "completed_stages": ["preflight"],
        "official_result": False,
        "q_coverage": {"expected_q_count": 8, "built_q_count": 0},
    }
    (output / "v20_partial_result.json").write_text(
        json.dumps(partial), encoding="utf-8"
    )
    (output / "task40_v10_p6_candidate_summary.json").write_text(
        json.dumps({"status": "CONTROLLED_STOP", "official_result": False}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": partial["run_id"],
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "physical_model_sha256": model_sha,
                "mesh_id": "TARGET_ORIGINAL_NY8",
                "scientific_input_sha256": V30_CANONICAL_INPUT_SHA256,
                "v31_input_identity": v31_identity,
                "v31_execution_contract_binding": {
                    "run_source_sha": source_sha,
                    "selector_path": str(selector_path),
                    "selector_sha256": selector_sha,
                    "input_identity": v31_identity,
                },
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "run_summary.json"
    summary_path.write_text(json.dumps({"result_classification": "controlled_stop"}), encoding="utf-8")
    monkeypatch.setattr(
        service,
        "_read_case",
        lambda _path: (
            "fixture",
            {
                "solver": {"preconditioner": V31_PROFILE},
                "execution": {"task40_target_heavy_authorized": False},
            },
        ),
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_input_identity",
        lambda *_args, **_kwargs: v31_identity,
    )
    monkeypatch.setattr(
        task40_v21_readonly_recheck,
        "validate_stage_receipt_semantics",
        lambda *_args, **_kwargs: {"fixture_stage_semantics": True},
    )

    checked = service._check_partial_result(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_output=output,
        expected_stop_stage="full",
    )

    assert checked["checker_passed"] is True, checked["errors"]
    assert checked["v31_reference_audit_status"] == "NOT_RUN_REFERENCE_NOT_COMPLETE"
    assert checked["v31_reference_product_recheck"] is None
    assert checked["checks"]["v31_reference_product_rechecked_or_truthfully_not_run"] is True


def _window(tmp_path: Path) -> FixedCampaignWindow:
    t0 = 1_800_000_000_000_000_000
    return FixedCampaignWindow(
        path=tmp_path / "window.json",
        sha256="a" * 64,
        payload={},
        anchor={
            "monotonic": 100.0,
            "boottime": 100.0,
            "utc_ns": t0,
            "boot_id": "test-boot",
        },
        t0_utc_ns=t0,
        deadline_utc_ns=t0 + 43_200_000_000_000,
        total_seconds=43_200.0,
        bootstrap_seconds=0.0,
        closeout_seconds=1_200.0,
    )


def _v31_worker_fixture(root: Path) -> tuple[dict, dict, dict, dict, str]:
    window_sha = "a" * 64
    run_source = "b" * 40
    source_at_entry = "c" * 40
    contract_sha = "d" * 64
    run_root = root / V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}"
    entry_root = root / V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_at_entry}"
    contract_path = run_root / "execution_contract_v31.approved.json"
    window_path = entry_root / "campaign_window_v31.json"
    selector_path = run_root / "q_csr_selector_v31.json"
    input_path = run_root / "stage_inputs/full/target_original_ny8_resource_pilot_v20.dat"
    donor = {
        "identity_sha256": "e" * 64,
        "manifest_relative_path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl/q0/manifest.json",
        "manifest_sha256": "f" * 64,
    }
    worklist = [
        {"q": 0, "action": "reuse accepted CSR/native producer; build one fresh live-bank factor"},
        *[dict(row) for row in V31_Q_WORKLIST],
    ]
    window = {
        "window_path": str(window_path),
        "window_sha256": window_sha,
        "source_at_entry": source_at_entry,
        "total_seconds": TASK40_V31_CAMPAIGN_SECONDS,
        "numeric_seconds": 42_000,
        "closeout_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
        "closeout_reserve_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
        "t0_utc": "2026-10-13T00:00:00Z",
        "numeric_cutoff_utc": "2026-10-13T11:40:00Z",
        "deadline_utc": "2026-10-13T12:00:00Z",
    }
    contract = {
        "schema": "task40extra.review_v31_execution_contract.v1",
        "status": "USER_APPROVED",
        "service_start_allowed": True,
        "source_freeze": {"source_sha": run_source, "branch": "task40extra_0p7nm_engineering", "clean": True},
        "preparation": {"accepted_q0_donor": donor, "q_csr_worklist": worklist},
        "execution": {
            "root": str(root),
            "profile": V31_PROFILE,
            "resources": dict(V31_RESOURCES),
            "window": window,
            "campaign_window_path": str(window_path),
            "campaign_window_sha256": window_sha,
            "run_source_sha": run_source,
            "selector_path": str(selector_path),
            "selector_sha256": "1" * 64,
            "input_path": str(input_path),
            "input_sha256": "2" * 64,
        },
    }
    selector_binding = {
        "schema": V31_Q_CSR_BINDING_SCHEMA,
        "selector_path": str(selector_path),
        "selector_sha256": "1" * 64,
    }
    factor_config = {
        "schema": V31_FACTOR_BANK_SCHEMA,
        "output_directory": str((run_root / "factor_bank").resolve()),
        "require_two_strict_rhs": True,
        "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
    }
    admission = {"schema": "task40extra.review_v31_target_admission.v1", "phase": "REFERENCE_ONLY"}
    imports = {"complete": {}, "numeric_pending": {}}
    binding = {
        "schema": V31_WORKER_BINDING_SCHEMA,
        "contract_path": str(contract_path),
        "contract_sha256": contract_sha,
        "execution_window_path": str(window_path),
        "execution_window_sha256": window_sha,
        "source_at_entry": source_at_entry,
        "run_source_sha": run_source,
        "q_csr_selector_binding": selector_binding,
        "factor_bank_config": factor_config,
        "accepted_q0_donor": donor,
        "q_csr_worklist": worklist,
        "q_csr_import_authorizations": imports,
        "target_admission_policy": admission,
    }
    payload = {
        "run_id": "task40extra_0p7nm_target_original_ny8_resource_pilot_v20",
        "solver": {"preconditioner": V31_PROFILE},
        "execution": {"task40_execution_stop_stage": "full", "task40_target_heavy_authorized": True},
        "provenance": {"source_path": str(input_path), "input_sha256": "2" * 64},
    }
    environment = {
        "TASK40_V31_STRICT_EXECUTION": "1",
        "TASK40_V31_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK40_V31_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(V31_RESOURCES["task_memory_max_bytes"]),
        "TASK40_V31_HOST_RESERVE_BYTES": str(V31_RESOURCES["host_reserve_bytes"]),
        "TASK40_V31_MEMORY_SWAP_MAX_BYTES": str(V31_RESOURCES["memory_swap_max_bytes"]),
    }
    return contract, binding, payload, environment, contract_sha


def test_v31_launcher_values_are_source_bound_native_and_resource_exact(tmp_path, monkeypatch):
    from src.runners import task40_v30_contract, task40_v31_contract

    source_sha = "b" * 40
    source_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_sha}"
    window_path = source_root / "campaign_window_v31.json"
    window_sha = "a" * 64
    contract = {
        "execution": {
            "root": str(tmp_path.resolve()),
            "resources": dict(V31_RESOURCES),
            "runtime_prefix": str(task40_v30_contract.V30_RUNTIME_RELATIVE),
            "abi_receipt_path": str(task40_v30_contract.V30_ABI_RECEIPT_RELATIVE),
            "jit_cache": str(task40_v30_contract.V30_JIT_CACHE_RELATIVE),
            "window": {"window_path": str(window_path), "window_sha256": window_sha},
            "campaign_window_path": str(window_path),
            "campaign_window_sha256": window_sha,
        }
    }
    contract_sha = "d" * 64
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )

    values = v31_launcher_values("pending.json", current_root=tmp_path)

    assert len(values) == 10
    assert values == (
        str(tmp_path.resolve()),
        str((tmp_path / task40_v30_contract.V30_RUNTIME_RELATIVE).resolve()),
        str((tmp_path / task40_v30_contract.V30_ABI_RECEIPT_RELATIVE).resolve()),
        str((tmp_path / task40_v30_contract.V30_JIT_CACHE_RELATIVE).resolve()),
        str(V31_RESOURCES["task_memory_max_bytes"]),
        contract_sha,
        str(window_path.resolve()),
        window_sha,
        str(V31_RESOURCES["host_reserve_bytes"]),
        "0",
    )

    contract["execution"]["runtime_prefix"] = "../foreign/runtime"
    with pytest.raises(ValueError, match="fixed native runtime path"):
        v31_launcher_values("pending.json", current_root=tmp_path)


def test_v31_same_window_new_source_contract_launcher_worker_and_campaign_route(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from scripts import task40_v20_service_workflow as workflow
    from src.runners import task40_v10_campaign as campaign
    from src.runners import task40_v30_contract, task40_v31_contract

    run_source = "b" * 40
    source_at_entry = "a" * 40
    run_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}"
    entry_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_at_entry}"
    run_root.mkdir(parents=True)
    entry_root.mkdir(parents=True)
    contract_path = run_root / "execution_contract_v31.approved.json"
    window_path = entry_root / "campaign_window_v31.json"
    input_path = run_root / "stage_inputs/full/target_original_ny8_resource_pilot_v20.dat"
    selector_path = run_root / "q_csr_selector_v31.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"source-qualified V31 stage input\n")
    selector_path.write_bytes(b"source-qualified V31 selector\n")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    selector_sha = hashlib.sha256(selector_path.read_bytes()).hexdigest()

    t0 = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
    t0_ns = int(t0.timestamp()) * 1_000_000_000
    cutoff = t0 + dt.timedelta(seconds=42_000)
    deadline = t0 + dt.timedelta(seconds=43_200)
    t0_text = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff_text = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline_text = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_id = "12345678-1234-1234-1234-123456789abc"
    review_path = tmp_path / V31_REVIEW_PATH
    review_path.parent.mkdir(parents=True)
    canonical_review = Path(__file__).resolve().parents[2] / V31_REVIEW_PATH
    review_path.write_bytes(canonical_review.read_bytes())
    window_payload = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": "task40extra_v31_all_q_reference_conditional_target_pilot",
        "authority": "User-approved Review V31 execution window",
        "active_review_sha": V31_REVIEW_COMMIT,
        "active_review_path": V31_REVIEW_PATH,
        "active_review_sha256": V31_REVIEW_SHA256,
        "source_at_entry": source_at_entry,
        "review_at_registration": V31_REVIEW_COMMIT,
        "t0_utc": t0_text,
        "numeric_cutoff_utc": cutoff_text,
        "deadline_utc": deadline_text,
        "campaign_seconds": TASK40_V31_CAMPAIGN_SECONDS,
        "numeric_cutoff_seconds": 42_000.0,
        "closeout_reserve_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(V31_STAGE_SCOPE),
        "forbidden_scope": [
            "automatic_cap_increase", "window_refresh", "parameter_or_accuracy_scan",
            "MUMPS_or_ABI_change", "OOC_or_BLR", "unrelated_project_mutation", "master_merge",
        ],
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
        "first_full_three_clock_sample": {
            "monotonic": 100.0,
            "boottime": 100.0,
            "utc_ns": t0_ns,
            "boot_id": boot_id,
        },
        "initial_boot_id": boot_id,
        "bootstrap_utc_elapsed_seconds": 0.0,
        "bootstrap_time_treatment": (
            "T0 begins before first preparation; UTC elapsed is charged; UNKNOWN is retained; "
            "null is not zero; Never refresh T0."
        ),
    }
    window_path.write_text(json.dumps(window_payload, sort_keys=True) + "\n")
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    approval = {
        "approved": True,
        "scope": "V31_WINDOW_43200_NUMERIC_42000_CLOSEOUT_1200",
        "window_sha256": window_sha,
        "evidence": "temporary fixture only; no real user approval",
    }
    contract = {
        "schema": task40_v31_contract.V31_CONTRACT_SCHEMA,
        "status": "USER_APPROVED",
        "registration_schema": task40_v31_contract.V31_REGISTRATION_SCHEMA,
        "service_start_allowed": True,
        "review": {
            "path": V31_REVIEW_PATH,
            "commit": V31_REVIEW_COMMIT,
            "sha256": V31_REVIEW_SHA256,
        },
        "source_freeze": {
            "required": True,
            "source_sha": run_source,
            "branch": task40_v31_contract.V31_BRANCH,
            "clean": True,
        },
        "preparation": {"accepted_q0_donor": {}, "q_csr_worklist": []},
        "user_approval": approval,
        "execution": {
            "root": str(tmp_path.resolve()),
            "profile": V31_PROFILE,
            "resources": dict(V31_RESOURCES),
            "window": {
                "window_path": str(window_path.resolve()),
                "window_sha256": window_sha,
                "source_at_entry": source_at_entry,
                "total_seconds": TASK40_V31_CAMPAIGN_SECONDS,
                "numeric_seconds": 42_000,
                "closeout_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
                "closeout_reserve_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
                "t0_utc": t0_text,
                "numeric_cutoff_utc": cutoff_text,
                "deadline_utc": deadline_text,
            },
            "campaign_window_path": str(window_path.resolve()),
            "campaign_window_sha256": window_sha,
            "run_source_sha": run_source,
            "runtime_prefix": str(task40_v30_contract.V30_RUNTIME_RELATIVE),
            "abi_receipt_path": str(task40_v30_contract.V30_ABI_RECEIPT_RELATIVE),
            "jit_cache": str(task40_v30_contract.V30_JIT_CACHE_RELATIVE),
            "input_path": str(input_path.resolve()),
            "input_sha256": input_sha,
            "selector_path": str(selector_path.resolve()),
            "selector_sha256": selector_sha,
        },
    }
    contract_path.write_text(json.dumps(contract, sort_keys=True) + "\n")
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    def git_output(args, *, cwd, text):
        if args[1:3] == ["branch", "--show-current"]:
            return f"{task40_v31_contract.V31_BRANCH}\n"
        if args[1:3] == ["rev-parse", "HEAD"]:
            return f"{run_source}\n"
        if args[1:4] == ["status", "--porcelain", "--untracked-files=normal"]:
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(task40_v31_contract.subprocess, "check_output", git_output)
    monkeypatch.setattr(
        task40_v31_contract.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )
    (validated, validated_sha) = task40_v31_contract.require_v31_execution_contract(
        contract_path,
        expected_sha256=contract_sha,
        current_root=tmp_path,
    )
    assert validated_sha == contract_sha
    assert validated["execution"]["window"]["source_at_entry"] == source_at_entry
    launch_values = task40_v31_contract.v31_launcher_values(
        contract_path,
        expected_sha256=contract_sha,
        current_root=tmp_path,
    )
    assert launch_values[6] == str(window_path.resolve())
    assert not (run_root / "campaign_window_v31.json").exists()

    monkeypatch.setattr(
        campaign,
        "__file__",
        str(tmp_path / "src/runners/task40_v10_campaign.py"),
    )
    monkeypatch.setattr(
        campaign,
        "clock_sample",
        lambda **_kwargs: {
            "monotonic": 101.0,
            "boottime": 101.0,
            "utc_ns": t0_ns + 1_000_000_000,
            "boot_id": boot_id,
        },
    )
    route = workflow._resolve_service_campaign(
        tmp_path,
        window_path,
        profile=V31_PROFILE,
        stop_stage="full",
        v31_contract=contract,
    )
    assert route["version"] == "V31"
    assert Path(route["path"]).resolve() == window_path.resolve()
    assert route["sha256"] == window_sha

    worker_contract, binding, payload, environment, worker_sha = _v31_worker_fixture(tmp_path)
    worker = validate_v31_worker_execution_binding(
        binding,
        contract=worker_contract,
        contract_sha256=worker_sha,
        resolved_payload=payload,
        source_sha="b" * 40,
        environment=environment,
        repo_root=tmp_path,
    )
    worker_entry_source = worker_contract["execution"]["window"]["source_at_entry"]
    assert worker["execution_window_path"].endswith(
        f"source_{worker_entry_source}/campaign_window_v31.json"
    )
    with pytest.raises(task40_v31_contract.V31ContractError, match="window, source, or resource"):
        validate_v31_worker_execution_binding(
            binding,
            contract=worker_contract,
            contract_sha256=worker_sha,
            resolved_payload=payload,
            source_sha="c" * 40,
            environment=environment,
            repo_root=tmp_path,
        )


def test_v31_all_q_dispatcher_keeps_its_contract_and_v30_route_disjoint(tmp_path, monkeypatch):
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
    )
    from src.runners import task40_v31_contract
    from src.solvers.task40_v20_registry import task40_v20_case

    run_source = "b" * 40
    contract_sha = "d" * 64
    source_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}"
    window_path = source_root / "campaign_window_v31.json"
    selector_path = source_root / "q_csr_selector_v31.json"
    input_path = source_root / "stage_inputs/full/target_original_ny8_resource_pilot_v20.dat"
    selector_sha = "1" * 64
    input_sha = "2" * 64
    window_sha = "a" * 64
    contract = {
        "execution": {
            "root": str(tmp_path.resolve()),
            "run_source_sha": run_source,
            "profile": V31_PROFILE,
            "resources": dict(V31_RESOURCES),
            "window": {
                "window_path": str(window_path),
                "window_sha256": window_sha,
            },
            "campaign_window_path": str(window_path),
            "campaign_window_sha256": window_sha,
            "selector_path": str(selector_path),
            "selector_sha256": selector_sha,
            "input_path": str(input_path),
            "input_sha256": input_sha,
        }
    }
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_input_identity",
        lambda *_args, **_kwargs: {
            "staged_input_sha256": input_sha,
            "scientific_input_sha256": "3" * 64,
        },
    )
    case = task40_v20_case(profile=V31_PROFILE)
    payload = {
        "run_id": case.run_id,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "method": {"kind": "full3d_iterative"},
        "solver": {
            "preconditioner": V31_PROFILE,
            "stage": case.solver_stage,
            "task40_reference_pc_strategy": TASK40_V15_REFERENCE_PC_STRATEGY,
            "task40_q_assembly_strategy": TASK40_Q_ASSEMBLY_ROW_TILE_V17,
            "task40_factor_lifecycle_strategy": TASK40_V19_FACTOR_LIFECYCLE_STRATEGY,
        },
        "execution": {
            "task40_execution_stop_stage": "full",
            "task40_target_heavy_authorized": True,
            "task40_v31_q_csr_binding": {
                "schema": V31_Q_CSR_BINDING_SCHEMA,
                "selector_path": (
                    V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}" / "q_csr_selector_v31.json"
                ).as_posix(),
                "selector_sha256": selector_sha,
            },
            "task40_v31_factor_bank_config": {
                "schema": V31_FACTOR_BANK_SCHEMA,
                "output_directory": (
                    V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}" / "factor_bank"
                ).as_posix(),
                "require_two_strict_rhs": True,
                "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
            },
        },
        "provenance": {"source_path": str(input_path), "input_sha256": input_sha},
    }
    environment = {
        "TASK40_V31_STRICT_EXECUTION": "1",
        "TASK40_V31_CONTRACT_PATH": str(
            source_root / "execution_contract_v31.approved.json"
        ),
        "TASK40_V31_CONTRACT_SHA256": contract_sha,
        "TASK40_V31_EXECUTION_WINDOW_PATH": str(window_path.resolve()),
        "TASK40_V31_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(V31_RESOURCES["task_memory_max_bytes"]),
        "TASK40_V31_HOST_RESERVE_BYTES": str(V31_RESOURCES["host_reserve_bytes"]),
        "TASK40_V31_MEMORY_SWAP_MAX_BYTES": "0",
    }

    route = require_v31_all_q_route(
        payload,
        source_sha=run_source,
        repo_root=tmp_path,
        environment=environment,
    )

    assert route["requested_factor_lifecycle_strategy"] == "ONE_Q_REFACTOR_V19"
    assert route["effective_factor_lifecycle_strategy"] == "ALL_Q_RESIDENT"
    assert route["input_identity"]["staged_input_sha256"] == input_sha
    assert route["contract_sha256"] == contract_sha

    payload["execution"]["task40_v30_q_csr_binding"] = dict(
        payload["execution"]["task40_v31_q_csr_binding"]
    )
    with pytest.raises(ValueError, match="only its complete V31 execution bindings"):
        require_v31_all_q_route(
            payload,
            source_sha=run_source,
            repo_root=tmp_path,
            environment=environment,
        )


def test_v31_dispatcher_passes_normalized_selector_to_validation_only_worker(
    tmp_path, monkeypatch
):
    from src.runners import task40_v10_worker, task40_v20_stage_runner
    from src.runners import task40_v31_contract

    contract, _binding, payload, environment, contract_sha = _v31_worker_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_source = contract["execution"]["run_source_sha"]
    source_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}"
    selector_path = source_root / "q_csr_selector_v31.json"
    payload["solver"].update(
        task40_reference_pc_strategy="V15_REFERENCE_PC_STRATEGY",
        task40_q_assembly_strategy="Q_ASSEMBLY_ROW_TILE_V17",
        task40_factor_lifecycle_strategy="ALL_Q_RESIDENT",
    )
    payload["execution"].update(
        task40_v31_q_csr_binding={
            "schema": V31_Q_CSR_BINDING_SCHEMA,
            "selector_path": selector_path.relative_to(tmp_path).as_posix(),
            "selector_sha256": "1" * 64,
        },
        task40_v31_factor_bank_config={
            "schema": V31_FACTOR_BANK_SCHEMA,
            "output_directory": (
                V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}" / "factor_bank"
            ).as_posix(),
            "require_two_strict_rhs": True,
            "second_rhs_formula": "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13",
        },
    )
    contract_path = Path(contract["execution"]["root"]) / V31_ARTIFACT_ROOT_RELATIVE / (
        f"source_{run_source}/execution_contract_v31.approved.json"
    )
    environment["TASK40_V31_CONTRACT_PATH"] = str(contract_path)
    environment["TASK40_V31_CONTRACT_SHA256"] = contract_sha
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_input_identity",
        lambda *_args, **_kwargs: {
            "staged_input_sha256": "2" * 64,
            "scientific_input_sha256": "3" * 64,
        },
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "validate_v31_worker_execution_binding",
        lambda *_args, **_kwargs: {"fixture_binding_validated": True},
    )
    monkeypatch.setattr(task40_v20_stage_runner, "__file__", str(tmp_path / "src/runners/stage.py"))
    monkeypatch.setattr(task40_v10_worker, "__file__", str(tmp_path / "src/runners/worker.py"))
    monkeypatch.setattr(task40_v20_stage_runner, "_exact_case", lambda _payload: (V31_PROFILE, "TARGET_ORIGINAL_NY8"))
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "_preflight",
        lambda *_args, **_kwargs: (
            {"run_id": payload["run_id"], "input_sha256": "2" * 64},
            [],
            [],
        ),
    )
    actual_worker = task40_v10_worker.run_task40_v10_p6_reference_worker

    def validation_only_worker(*args, **kwargs):
        kwargs["_v31_entry_validation_only"] = True
        return actual_worker(*args, **kwargs)

    monkeypatch.setattr(
        task40_v10_worker,
        "run_task40_v10_p6_reference_worker",
        validation_only_worker,
    )

    result = task40_v20_stage_runner.run_task40_v20_stage(
        payload,
        tmp_path / "stage-output",
        source_sha=run_source,
        v31_requested_factor_lifecycle_strategy="ONE_Q_REFACTOR_V19",
        v31_effective_factor_lifecycle_strategy="ALL_Q_RESIDENT",
    )

    assert result["status"] == "V31_ROUTE_VALIDATED_NO_FE_HOOKS"
    assert result["fe_hooks_invoked"] is False
    assert result["jit_hooks_invoked"] is False


def test_v31_closeout_allows_missing_numerical_output_only_for_bound_failure(
    tmp_path, monkeypatch
):
    from scripts import task40_v20_service_workflow as service
    from src.runners import task40_v31_contract

    root = tmp_path / "repo"
    evidence = root / "benchmarks/artifacts/run-evidence"
    evidence.mkdir(parents=True)
    run_directory = root / "results" / "v31-attempt"
    run_directory.mkdir(parents=True)
    input_path = run_directory / "stage.dat"
    run_id = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
    input_path.write_text(
        f'run_id = "{run_id}"\n[solver]\npreconditioner = "{V31_PROFILE}"\n',
        encoding="utf-8",
    )
    numerical_path = run_directory / "numerical-output"
    summary_path = run_directory / "run_summary.json"
    manifest_path = run_directory / "run_manifest.json"
    source_sha = "b" * 40
    input_sha = service._sha256_file(input_path)
    window_path = root / "campaign_window_v31.json"
    window_path.write_text("approved fixture window\n", encoding="utf-8")
    window_sha = service._sha256_file(window_path)
    contract = {
        "execution": {
            "window": {"window_path": str(window_path), "window_sha256": window_sha}
        }
    }
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        lambda *_args, **_kwargs: (contract, "d" * 64),
    )
    summary_path.write_text(
        json.dumps(
            {
                "status": "finished",
                "result_classification": "WORKER_FAILED",
                "exit_status": 4,
                "run_id": run_id,
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "numerical_output_directory": str(numerical_path),
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "input_path": str(input_path),
                "task40_v20_campaign": {
                    "window_path": str(window_path),
                    "window_sha256": window_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    command = [
        str(runtime / "bin/python"),
        str(root / "scripts/task40_v20_service_workflow.py"),
        "check-partial",
        "--input",
        str(input_path),
        "--summary",
        str(summary_path),
        "--manifest",
        str(manifest_path),
        "--numerical-output",
        str(numerical_path),
        "--stop-stage",
        "full",
        "--output",
        str(evidence / "partial_checker_result.json"),
    ]
    source_state = {"branch": "task40extra_0p7nm_engineering", "source_sha": source_sha, "clean": True}

    authorization = service._task40_v31_closeout_checker_authorization(
        command=command,
        checker_kind="task40_v20_partial_receipt_checker",
        runtime_prefix=runtime,
        repo_root=root,
        evidence_directory=evidence,
        campaign_sha256=window_sha,
        contract_path=root / "approved-contract.json",
        source_state=source_state,
        profile=V31_PROFILE,
    )

    assert authorization["schema"].endswith("authorization.v2")
    assert authorization["input_paths"] == [
        str(input_path.resolve()),
        str(summary_path.resolve()),
        str(manifest_path.resolve()),
    ]
    with pytest.raises(ValueError, match="paths are not bound"):
        service._task40_v30_closeout_checker_authorization(
            command=command,
            checker_kind="task40_v20_partial_receipt_checker",
            runtime_prefix=runtime,
            repo_root=root,
            evidence_directory=evidence,
            campaign_sha256=window_sha,
            contract_sha256="c" * 64,
            source_state=source_state,
            profile=V31_PROFILE,
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["result_classification"] = "worker_exit0"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="paths are not bound"):
        service._task40_v31_closeout_checker_authorization(
            command=command,
            checker_kind="task40_v20_partial_receipt_checker",
            runtime_prefix=runtime,
            repo_root=root,
            evidence_directory=evidence,
            campaign_sha256=window_sha,
            contract_path=root / "approved-contract.json",
            source_state=source_state,
            profile=V31_PROFILE,
        )


def test_v31_closeout_supervisor_starts_samples_and_clears_fake_checker(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from benchmarks import subreaper_watchdog as watchdog
    from scripts import task40_v20_service_workflow as service
    from src.io import physical_intermediate_profile
    from src.runners import task40_v10_campaign, task40_v31_contract
    from src.runners.workflow_timebase import clock_sample

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        task40_v10_campaign,
        "__file__",
        str(repo_root / "src/runners/task40_v10_campaign.py"),
    )
    source_sha = "b" * 40
    source_root = repo_root / V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_sha}"
    window_path = source_root / "campaign_window_v31.json"
    window_path.parent.mkdir(parents=True)
    anchor = clock_sample(include_boot_id=True)

    def utc_iso(timestamp_ns: int) -> str:
        seconds, nanos = divmod(timestamp_ns, 1_000_000_000)
        stamp = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        return f"{stamp}.{nanos:09d}Z"

    t0_ns = int(anchor["utc_ns"])
    window_payload = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": "task40extra_v31_all_q_reference_conditional_target_pilot",
        "authority": "test-only V31 closeout supervisor fixture",
        "active_review_sha": V31_REVIEW_COMMIT,
        "active_review_path": V31_REVIEW_PATH,
        "active_review_sha256": V31_REVIEW_SHA256,
        "source_at_entry": "c" * 40,
        "review_at_registration": V31_REVIEW_COMMIT,
        "t0_utc": utc_iso(t0_ns),
        "numeric_cutoff_utc": utc_iso(t0_ns + 42_000_000_000_000),
        "deadline_utc": utc_iso(t0_ns + 43_200_000_000_000),
        "campaign_seconds": TASK40_V31_CAMPAIGN_SECONDS,
        "numeric_cutoff_seconds": 42_000.0,
        "closeout_reserve_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(V31_STAGE_SCOPE),
        "forbidden_scope": [
            "automatic_cap_increase",
            "window_refresh",
            "parameter_or_accuracy_scan",
            "MUMPS_or_ABI_change",
            "OOC_or_BLR",
            "unrelated_project_mutation",
            "master_merge",
        ],
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
        "bootstrap_utc_elapsed_seconds": 0.0,
        "bootstrap_time_treatment": "test fixture anchor equals T0",
        "initial_boot_id": anchor["boot_id"],
        "first_full_three_clock_sample": dict(anchor),
    }
    window_bytes = (json.dumps(window_payload, sort_keys=True) + "\n").encode()
    window_path.write_bytes(window_bytes)
    window_sha = hashlib.sha256(window_bytes).hexdigest()
    contract_sha = "d" * 64
    contract = {
        "execution": {
            "resources": dict(V31_RESOURCES),
            "jit_cache": str(tmp_path / "jit-cache"),
            "window": {
                "window_path": str(window_path),
                "window_sha256": window_sha,
                "closeout_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
            },
        }
    }
    monkeypatch.setattr(
        task40_v10_campaign,
        "_validate_v31_campaign_registration",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setenv("TASK40_V31_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK40_V31_CONTRACT_PATH", str(source_root / "execution_contract_v31.approved.json"))
    monkeypatch.setenv("TASK40_V31_CONTRACT_SHA256", contract_sha)
    marker = "native_linux_imports_only:" + "e" * 64
    monkeypatch.setattr(service, "_qualified_activation_identity", lambda _env: marker)
    monkeypatch.setattr(
        service,
        "_v31_live_resource_gate",
        lambda *_args, **_kwargs: {"passed": True, "fixture": True},
    )
    authorization = {
        "schema": "task40extra.review_v31_closeout_checker_authorization.v2",
        "phase": "closeout",
        "command_sha256": "f" * 64,
        "source_sha": source_sha,
        "source_branch": "task40extra_0p7nm_engineering",
        "source_clean": True,
    }
    monkeypatch.setattr(
        service,
        "_task40_v31_closeout_checker_authorization",
        lambda **_kwargs: authorization,
    )

    def validate_closeout(*, command, campaign, authorization, worker_environment):
        assert command == request["command"]
        assert campaign.sha256 == window_sha
        assert authorization == request["closeout_authorization"]
        assert worker_environment["TASK40_V31_STRICT_EXECUTION"] == "1"
        return dict(authorization)

    monkeypatch.setattr(watchdog, "_validate_campaign_closeout_authorization", validate_closeout)
    monkeypatch.setattr(
        physical_intermediate_profile,
        "profile_facts",
        lambda _profile: {
            "resources": {
                "watchdog_memory_policy": watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY,
                "pss_sampling_policy": "sampled",
                "process_tree_rss_cap_bytes": 1 << 30,
                "workflow_seconds": 1200,
                "campaign_closeout_reserve_seconds": 1200,
            }
        },
    )
    monkeypatch.setattr(
        watchdog,
        "memory_envelope",
        lambda *_args, **_kwargs: {
            "launch_cap_bytes": 1 << 40,
            "effective_available_bytes": 1 << 40,
            "effective_available_after_reserves_bytes": 1 << 40,
            "reserve_bytes": 0,
            "reserve_domains_separated": True,
        },
    )
    monkeypatch.setattr(
        watchdog,
        "cgroup_snapshot",
        lambda *_args, **_kwargs: {
            "dedicated_job_cgroup": True,
            "readable": True,
            "swap_current_bytes": 0,
        },
    )
    sampler_calls = []

    def sample_tree(*_args, **_kwargs):
        sampler_calls.append(1)
        children = watchdog._children()
        return {
            "rss_bytes": 1024,
            "swap_bytes": 0,
            "all_status_readable": True,
            "identity_complete": True,
            "identity_count": len(children) + 1,
            "members": [
                {"pid": pid, "start_ticks": identity[1]}
                for pid, identity in children.items()
            ],
        }

    monkeypatch.setattr(watchdog, "process_tree_snapshot", sample_tree)
    monkeypatch.setattr(
        watchdog.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(prctl=lambda *_prctl_args: 0),
    )
    monkeypatch.setattr(watchdog.signal, "signal", lambda *_args, **_kwargs: None)

    runtime_prefix = Path(sys.prefix).resolve()
    evidence = tmp_path / "evidence"
    command = [
        str(sys.executable),
        "-c",
        "import time; print('v31 fake checker complete', flush=True); time.sleep(0.35)",
    ]
    request = {
        "command": command,
        "checker_kind": "task40_v20_partial_receipt_checker",
        "evidence_directory": str(evidence),
        "runtime_prefix": str(runtime_prefix),
        "activation_marker": marker,
        "numeric_environment": {},
        "service_parent_pid": os.getppid(),
        "service_cgroup_membership": "0::/fixture",
        "repo_root": str(repo_root),
        "campaign_window": str(window_path),
        "campaign_sha256": window_sha,
        "campaign_accounting": str(tmp_path / "campaign_accounting_v10.jsonl"),
        "campaign_phase": "closeout",
        "closeout_authorization": authorization,
        "source_state": {"branch": "task40extra_0p7nm_engineering", "source_sha": source_sha, "clean": True},
        "profile": V31_PROFILE,
        "v31_resource_gate": {"passed": True},
        "v29_resource_gate": None,
        "v30_resource_gate": None,
    }

    result = service._run_required_checker_supervision(request)

    summary = json.loads(Path(result["details"]["watchdog_summary_path"]).read_text())
    assert result["return_code"] == 0
    assert result["details"]["watchdog_classification"] == "COMPLETED"
    assert result["details"]["supervision"]["campaign_phase"] == "closeout"
    assert result["details"]["v31_contract_resource_gate"]["fixture"] is True
    assert summary["task40_v10_campaign"]["phase"] == "closeout"
    assert summary["process_tree_samples"] >= 1
    assert summary["job_cgroup_swap"]["passed"] is True
    assert len(sampler_calls) >= 2
    assert summary["descendants_cleared"] is True


def test_campaign_phase_budgets_preserve_numeric_cutoff_and_allow_closeout(tmp_path):
    window = _window(tmp_path)
    cutoff_ns = window.t0_utc_ns + 42_000_000_000_000

    assert window.remaining_seconds(
        phase="numeric",
        cumulative_charged_seconds=42_000.0,
        now_utc_ns=cutoff_ns,
    ) == 0.0
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=42_000.0,
        now_utc_ns=cutoff_ns,
    ) == 1_200.0
    assert window.phase_expired(
        phase="numeric",
        cumulative_charged_seconds=42_000.0,
        now_utc_ns=cutoff_ns,
    ) is True
    assert window.phase_expired(
        phase="closeout",
        cumulative_charged_seconds=42_000.0,
        now_utc_ns=cutoff_ns,
    ) is False
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=42_000.0,
        now_utc_ns=cutoff_ns,
        termination_reserve_seconds=60.0,
    ) == 1_140.0
    assert window.phase_expired(
        phase="closeout",
        cumulative_charged_seconds=43_140.0,
        now_utc_ns=window.t0_utc_ns + 43_140_000_000_000,
        termination_reserve_seconds=60.0,
    ) is True
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=42_500.0,
        now_utc_ns=cutoff_ns + 500_000_000_000,
        sub_budget_seconds=400.0,
    ) == 400.0
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=43_200.0,
        now_utc_ns=window.deadline_utc_ns,
    ) == 0.0
    assert window.phase_expired(
        phase="closeout",
        cumulative_charged_seconds=43_200.0,
        now_utc_ns=window.deadline_utc_ns,
    ) is True
    with pytest.raises(ValueError, match="numeric or closeout"):
        window.remaining_seconds(
            phase="numerical-ish",
            cumulative_charged_seconds=0.0,
            now_utc_ns=window.t0_utc_ns,
        )


def test_v30_closeout_authorization_binds_exact_registered_checker_and_inputs(tmp_path):
    root = tmp_path / "repo"
    evidence = root / "artifacts" / "run"
    numeric = evidence / "numeric"
    numeric.mkdir(parents=True)
    runtime = tmp_path / "runtime"
    packet = numeric / "v10_candidate_official_output.json"
    packet.write_text("{}", encoding="utf-8")
    source = {"branch": "task40extra_0p7nm_engineering", "source_sha": "b" * 40, "clean": True}

    authorization = _task40_v30_closeout_checker_authorization(
        command=[
            str(runtime / "bin/python"),
            "-m",
            "src.runners.task40_v10_output_checker",
            str(packet),
            "--expected-channel-count",
            str(V30_CHANNEL_COUNT),
        ],
        checker_kind="task40_v10_independent_output_checker",
        runtime_prefix=runtime,
        repo_root=root,
        evidence_directory=evidence,
        campaign_sha256="a" * 64,
        contract_sha256="c" * 64,
        source_state=source,
        profile=V30_PROFILE,
    )
    assert authorization["phase"] == "closeout"
    assert authorization["purpose"] == "registered_read_only_required_checker"
    assert authorization["campaign_window_sha256"] == "a" * 64
    assert authorization["expected_channel_count"] == V30_CHANNEL_COUNT
    assert len(authorization["command_sha256"]) == 64
    assert authorization["input_paths"] == [str(packet.resolve())]

    with pytest.raises(ValueError, match="registered official output checker"):
        _task40_v30_closeout_checker_authorization(
            command=[str(runtime / "bin/python"), "-m", "pytest", "-q"],
            checker_kind="task40_v10_independent_output_checker",
            runtime_prefix=runtime,
            repo_root=root,
            evidence_directory=evidence,
            campaign_sha256="a" * 64,
            contract_sha256="c" * 64,
            source_state=source,
            profile=V30_PROFILE,
        )


def test_v30_partial_checker_closeout_binds_all_input_paths(tmp_path):
    root = tmp_path / "repo"
    evidence = root / "artifacts" / "run"
    evidence.mkdir(parents=True)
    numerical = root / "artifacts" / "run_data"
    numerical.mkdir(parents=True)
    runtime = tmp_path / "runtime"
    input_path = root / "input.json"
    summary_path = root / "summary.json"
    manifest_path = root / "manifest.json"
    for path in (input_path, summary_path, manifest_path):
        path.write_text("{}", encoding="utf-8")
    output_path = evidence / "partial_checker_result.json"
    command = [
        str(runtime / "bin/python"),
        "scripts/task40_v20_service_workflow.py",
        "check-partial",
        "--input",
        str(input_path),
        "--summary",
        str(summary_path),
        "--manifest",
        str(manifest_path),
        "--numerical-output",
        str(numerical),
        "--stop-stage",
        "full",
        "--output",
        str(output_path),
    ]
    authorization = _task40_v30_closeout_checker_authorization(
        command=command,
        checker_kind="task40_v20_partial_receipt_checker",
        runtime_prefix=runtime,
        repo_root=root,
        evidence_directory=evidence,
        campaign_sha256="a" * 64,
        contract_sha256="c" * 64,
        source_state={"branch": "task40extra_0p7nm_engineering", "source_sha": "b" * 40, "clean": True},
        profile=V30_PROFILE,
    )
    assert authorization["phase"] == "closeout"
    assert authorization["input_paths"] == [
        str(input_path.resolve()),
        str(summary_path.resolve()),
        str(manifest_path.resolve()),
    ]

    command[2] = "run-case"
    with pytest.raises(ValueError, match="registered partial-receipt checker"):
        _task40_v30_closeout_checker_authorization(
            command=command,
            checker_kind="task40_v20_partial_receipt_checker",
            runtime_prefix=runtime,
            repo_root=root,
            evidence_directory=evidence,
            campaign_sha256="a" * 64,
            contract_sha256="c" * 64,
            source_state={"branch": "task40extra_0p7nm_engineering", "source_sha": "b" * 40, "clean": True},
            profile=V30_PROFILE,
        )


def test_watchdog_rejects_numeric_command_with_closeout_phase(tmp_path):
    with pytest.raises(ValueError, match="closeout phase requires"):
        _validate_campaign_closeout_authorization(
            command=["/qualified/python", "-m", "src.runners.task40_v20_worker"],
            campaign=_window(tmp_path),
            authorization=None,
            worker_environment={},
        )


def test_v31_same_window_resume_keeps_original_source_and_updates_only_run_source(tmp_path):
    window_path = tmp_path / "campaign_window_v31.json"
    window_payload = {"t0_utc": "2026-10-13T00:00:00Z"}
    window_path.write_text(json.dumps(window_payload) + "\n", encoding="utf-8")
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    entry_source = "a" * 40
    first_run_source = "b" * 40
    resumed_run_source = "c" * 40
    t0 = "2026-10-13T00:00:00Z"
    cutoff = "2026-10-13T11:40:00Z"
    deadline = "2026-10-13T12:00:00Z"
    registration = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": "task40extra_v31_all_q_reference_conditional_target_pilot",
        "authority": "User-approved Review V31 execution window",
        "active_review_sha": V31_REVIEW_COMMIT,
        "active_review_path": V31_REVIEW_PATH,
        "active_review_sha256": V31_REVIEW_SHA256,
        "source_at_entry": entry_source,
        "review_at_registration": V31_REVIEW_COMMIT,
        "t0_utc": t0,
        "numeric_cutoff_utc": cutoff,
        "deadline_utc": deadline,
        "campaign_seconds": TASK40_V31_CAMPAIGN_SECONDS,
        "numeric_cutoff_seconds": 42_000.0,
        "closeout_reserve_seconds": TASK40_V31_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(V31_STAGE_SCOPE),
        "forbidden_scope": [
            "automatic_cap_increase", "window_refresh", "parameter_or_accuracy_scan",
            "MUMPS_or_ABI_change", "OOC_or_BLR", "unrelated_project_mutation", "master_merge",
        ],
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
    }

    def contract_for(run_source: str) -> dict:
        window = {
            "window_path": str(window_path),
            "window_sha256": window_sha,
            "source_at_entry": entry_source,
            "t0_utc": t0,
            "numeric_cutoff_utc": cutoff,
            "deadline_utc": deadline,
        }
        return {
            "status": "USER_APPROVED",
            "source_freeze": {"source_sha": run_source},
            "execution": {"window": window, "run_source_sha": run_source},
            "user_approval": {
                "approved": True,
                "scope": "V31_WINDOW_43200_NUMERIC_42000_CLOSEOUT_1200",
                "window_sha256": window_sha,
            },
        }

    first = contract_for(first_run_source)
    resumed = contract_for(resumed_run_source)
    _validate_v31_campaign_registration(window_path, window_sha, registration, first)
    _validate_v31_campaign_registration(window_path, window_sha, registration, resumed)
    assert first["execution"]["window"] == resumed["execution"]["window"]
    assert first["source_freeze"]["source_sha"] != resumed["source_freeze"]["source_sha"]
    assert registration["source_at_entry"] == entry_source

    tampered = contract_for(resumed_run_source)
    tampered["execution"]["window"]["source_at_entry"] = resumed_run_source
    with pytest.raises(ValueError, match="campaign identity or scope changed"):
        _validate_v31_campaign_registration(window_path, window_sha, registration, tampered)


def test_v31_approved_prepare_failure_retry_preserves_first_t0(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from src.runners import task40_v31_contract as contract_mod
    from src.runners import workflow_timebase
    from src.runners.task40_v30_contract import (
        V30_ARTIFACT_ROOT_RELATIVE,
        V30_CANONICAL_INPUT_RELATIVE,
    )

    root = tmp_path.resolve()
    repository_root = Path(__file__).resolve().parents[2]
    real_prepare_pending = contract_mod.prepare_v31_pending_package
    source_sha = "b" * 40
    pending_directory = (
        root
        / contract_mod.V31_PREPARATION_RELATIVE
        / "v31_pending_package"
        / f"source_{source_sha}"
    )
    pending_directory.mkdir(parents=True)
    receipt = {
        "schema": contract_mod.V31_USER_APPROVAL_EVIDENCE_SCHEMA,
        "origin": "direct_user_message",
        "approved": True,
        "scope": contract_mod.V31_APPROVAL_SCOPE,
        "review_sha256": contract_mod.V31_REVIEW_SHA256,
        "source_sha": source_sha,
        "execution_root": str(root),
        "user_message": "fixture-only approval evidence",
    }
    receipt_path = pending_directory / "user_approval_v31.receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    review_path = root / contract_mod.V31_REVIEW_PATH
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_bytes((repository_root / contract_mod.V31_REVIEW_PATH).read_bytes())

    def fake_check_output(args, *, cwd, text):
        assert cwd == root and text is True
        if args == ["git", "branch", "--show-current"]:
            return f"{contract_mod.V31_BRANCH}\n"
        if args == ["git", "rev-parse", "HEAD"]:
            return f"{source_sha}\n"
        if args == ["git", "status", "--porcelain", "--untracked-files=normal"]:
            return ""
        raise AssertionError(f"unexpected git probe: {args!r}")

    def fake_run(args, *, cwd, check):
        assert cwd == root and check is False
        assert args == [
            "git",
            "merge-base",
            "--is-ancestor",
            contract_mod.V31_REVIEW_COMMIT,
            "HEAD",
        ]
        return SimpleNamespace(returncode=0)

    sample = {
        "utc_ns": 1_800_000_000_123_456_789,
        "monotonic": 123.5,
        "boottime": 124.0,
        "boot_id": "12345678-1234-1234-1234-123456789abc",
    }
    samples = []

    def fake_clock_sample(*, include_boot_id):
        assert include_boot_id is True
        samples.append(dict(sample))
        return dict(sample)

    pending_attempts = []

    def fail_pending_preparation(**kwargs):
        pending_attempts.append(kwargs)
        raise RuntimeError("fixture prep failure")

    monkeypatch.setattr(contract_mod.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(contract_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(workflow_timebase, "clock_sample", fake_clock_sample)
    monkeypatch.setattr(contract_mod, "prepare_v31_pending_package", fail_pending_preparation)

    with pytest.raises(RuntimeError, match="fixture prep failure"):
        contract_mod.prepare_v31_approved_package(
            repo_root=root,
            pending_directory=pending_directory,
            approval_receipt=receipt_path,
        )

    window_path = (
        root
        / contract_mod.v31_source_artifact_relative(source_sha)
        / "campaign_window_v31.json"
    )
    anchor_path = (
        root
        / contract_mod.V31_PREPARATION_RELATIVE
        / "t0_anchors"
        / f"source_{source_sha}.json"
    )
    window_bytes_after_first_failure = window_path.read_bytes()
    anchor_bytes_after_first_failure = anchor_path.read_bytes()

    with pytest.raises(RuntimeError, match="fixture prep failure"):
        contract_mod.prepare_v31_approved_package(
            repo_root=root,
            pending_directory=pending_directory,
            approval_receipt=receipt_path,
        )

    assert len(samples) == 1
    assert len(pending_attempts) == 2
    assert window_path.read_bytes() == window_bytes_after_first_failure
    assert anchor_path.read_bytes() == anchor_bytes_after_first_failure
    window = json.loads(window_bytes_after_first_failure)
    anchor = json.loads(anchor_bytes_after_first_failure)
    assert window["first_full_three_clock_sample"] == sample
    assert anchor["first_full_three_clock_sample"] == sample
    assert window["user_approval_receipt_sha256"] == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()

    canonical_path = root / V30_CANONICAL_INPUT_RELATIVE
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes((repository_root / V30_CANONICAL_INPUT_RELATIVE).read_bytes())
    selector_donor = root / V30_ARTIFACT_ROOT_RELATIVE / "q0_selector_v30_partial.json"
    selector_donor.parent.mkdir(parents=True, exist_ok=True)
    selector_donor.write_text(
        json.dumps({"schema": "fixture.v30_q0_selector.v1", "q": 0}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        contract_mod, "prepare_v31_pending_package", real_prepare_pending
    )
    approved_package = contract_mod.prepare_v31_approved_package(
        repo_root=root,
        pending_directory=pending_directory,
        approval_receipt=receipt_path,
    )

    assert len(samples) == 1
    assert len(pending_attempts) == 2
    assert approved_package["status"] == "USER_APPROVED_WINDOW_RESUMED_PREPARATION"
    assert approved_package["new_window_created"] is False
    assert approved_package["t0_refreshed"] is False
    assert Path(approved_package["window"]["path"]).read_bytes() == window_bytes_after_first_failure
    assert anchor_path.read_bytes() == anchor_bytes_after_first_failure

    approved_contract_path = Path(approved_package["contract"]["path"])
    approved_contract, approved_sha = contract_mod.require_v31_execution_contract(
        approved_contract_path,
        expected_sha256=approved_package["contract"]["sha256"],
        current_root=root,
    )
    assert approved_sha == approved_package["contract"]["sha256"]
    launcher_values = contract_mod.v31_launcher_values(
        approved_contract_path,
        expected_sha256=approved_sha,
        current_root=root,
    )
    assert launcher_values[0] == str(root)
    assert launcher_values[5] == approved_sha
    assert launcher_values[7] == approved_package["window"]["sha256"]

    from src.runners import task40_v10_campaign as campaign

    monkeypatch.setattr(
        campaign,
        "__file__",
        str(root / "src/runners/task40_v10_campaign.py"),
    )
    monkeypatch.setattr(
        campaign,
        "clock_sample",
        lambda *, include_boot_id: dict(sample),
    )
    campaign_window = campaign.load_fixed_campaign_window(
        approved_package["window"]["path"],
        require_current_boot=True,
        v31_contract=approved_contract,
    )
    assert campaign_window is not None
    window_payload = json.loads(window_bytes_after_first_failure)
    campaign._validate_v31_campaign_registration(
        Path(approved_package["window"]["path"]),
        approved_package["window"]["sha256"],
        window_payload,
        approved_contract,
    )

    commands = approved_package["commands"]
    assert "prepare-v31-approved" in commands[
        "prepare_approved_package_after_explicit_user_approval"
    ]
    assert "scripts/run_case_in_user_service.sh" in commands[
        "service_after_explicit_new_window_approval"
    ]
    assert "$v31_root/execution_contract_v31.approved.json" in commands[
        "service_after_explicit_new_window_approval"
    ]
    v31_unit_template = (
        "myfenics-case-task40-v31-all-q-reference-${v31_source_sha:0:12}"
    )
    assert f'v31_unit="{v31_unit_template}"' in commands[
        "service_after_explicit_new_window_approval"
    ]
    v31_unit = v31_unit_template.replace(
        "${v31_source_sha:0:12}",
        approved_contract["source_freeze"]["source_sha"][:12],
    )
    from src.runners import task038_launcher

    app_slice = Path(
        "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice"
    )
    assert task038_launcher._is_v28_user_service_cgroup(
        app_slice / f"{v31_unit}.service"
    )
    assert not task038_launcher._is_v28_user_service_cgroup(
        app_slice
        / f"task40-v31-all-q-reference-{approved_contract['source_freeze']['source_sha'][:12]}.service"
    )
    assert "src.runners.task40_v10_output_checker" in commands[
        "official_checker_after_valid_output"
    ]
    assert "--expected-channel-count 32060" in commands[
        "official_checker_after_valid_output"
    ]
    assert "check-partial" in commands["partial_receipt_checker_after_controlled_stop"]
