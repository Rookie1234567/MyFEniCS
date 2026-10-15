import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from scripts.task40_v20_service_workflow import (
    _task40_v30_closeout_checker_authorization,
    _v31_missing_numerical_output_is_bound_worker_failure,
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


def _old_v30_q0_selector_fixture(root: Path, source_root: Path) -> tuple[dict, dict, dict]:
    from src.runners.task40_v30_contract import V30_Q0_DONOR
    from src.solvers.task40_v30_qualified_q_csr import (
        V30_Q0_LEGACY_IMPORT_SCHEMA,
        V30_Q_CSR_SELECTOR_SCHEMA,
    )

    manifest_relative = Path(V30_Q0_DONOR["manifest_relative_path"])
    native_relative = Path(V30_Q0_DONOR["native_qualification_relative_path"])
    for relative in (manifest_relative, native_relative):
        source = source_root / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    manifest = json.loads((root / manifest_relative).read_text(encoding="utf-8"))
    native = json.loads((root / native_relative).read_text(encoding="utf-8"))
    fill_identity = manifest["numeric_fill_identity"]["execution_identity"]
    pattern_record = native["original_pattern_manifest"]
    pattern_path = Path(pattern_record["path"])
    if pattern_path.is_absolute():
        pattern_relative = pattern_path.relative_to(source_root).as_posix()
    else:
        pattern_relative = pattern_path.as_posix()
    old_legacy_identity = {
        "input_sha256": fill_identity["input_sha256"],
        "physical_model_sha256": fill_identity["physical_model_sha256"],
        "mode_manifest_sha256": fill_identity["mode_manifest_sha256"],
        "manifest_sha256": V30_Q0_DONOR["manifest_sha256"],
        "native_qualification_sha256": V30_Q0_DONOR["native_qualification_sha256"],
    }
    selector = {
        "schema": V30_Q_CSR_SELECTOR_SCHEMA,
        "profile": V31_PROFILE,
        "q_csr_entries": [
            {
                "q_index": 0,
                "twist_index": 0,
                "shape": manifest["shape"],
                "operator_identity": {"fixture": "preserved"},
                "matrix_source_identity": {
                    "source_sha": fill_identity["source_sha"],
                    "window_sha256": fill_identity["campaign_window_sha256"],
                },
                "execution_identity": {
                    "source_sha": "e" * 40,
                    "window_sha256": "f" * 64,
                },
                "csr_manifest": {
                    "path": manifest_relative.as_posix(),
                    "sha256": V30_Q0_DONOR["manifest_sha256"],
                },
                "native_qualification": {
                    "path": native_relative.as_posix(),
                    "sha256": V30_Q0_DONOR["native_qualification_sha256"],
                    "status": V30_Q0_DONOR["native_qualification_status"],
                },
                "legacy_q0_import": {
                    "schema": V30_Q0_LEGACY_IMPORT_SCHEMA,
                    "v28_identity": old_legacy_identity,
                    "original_pattern_manifest": {
                        "path": pattern_relative,
                        "sha256": pattern_record["sha256"],
                    },
                },
            }
        ],
    }
    return selector, manifest, native


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
        "review": {
            "path": V31_REVIEW_PATH,
            "commit": V31_REVIEW_COMMIT,
            "sha256": V31_REVIEW_SHA256,
        },
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


@pytest.mark.parametrize("review_version", ["V32", "V33"])
def test_v32_v33_service_campaign_resolves_original_entry_window_with_current_contract(
    tmp_path, monkeypatch, review_version
):
    from scripts import task40_v20_service_workflow as workflow
    from src.runners import task40_v10_campaign as campaign
    from src.runners import task40_v31_contract

    total_seconds = getattr(task40_v31_contract, f"{review_version}_TOTAL_SECONDS")
    numeric_seconds = getattr(task40_v31_contract, f"{review_version}_NUMERIC_SECONDS")
    closeout_seconds = getattr(task40_v31_contract, f"{review_version}_CLOSEOUT_SECONDS")
    review_commit = getattr(task40_v31_contract, f"{review_version}_REVIEW_COMMIT")
    review_path = getattr(task40_v31_contract, f"{review_version}_REVIEW_PATH")
    review_sha256 = getattr(task40_v31_contract, f"{review_version}_REVIEW_SHA256")
    approval_scope = getattr(task40_v31_contract, f"{review_version}_APPROVAL_SCOPE")
    stage_scope = getattr(task40_v31_contract, f"{review_version}_STAGE_SCOPE")
    run_source = "b" * 40
    source_at_entry = "a" * 40
    window_path = (
        tmp_path
        / task40_v31_contract.v31_source_artifact_relative(source_at_entry)
        / f"campaign_window_{review_version.lower()}.json"
    )
    window_path.parent.mkdir(parents=True)

    t0 = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
    t0_ns = int(t0.timestamp()) * 1_000_000_000
    cutoff = t0 + dt.timedelta(seconds=numeric_seconds)
    deadline = t0 + dt.timedelta(seconds=total_seconds)
    t0_text = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff_text = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    deadline_text = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_id = "12345678-1234-1234-1234-123456789abc"
    payload = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": f"task40extra_{review_version.lower()}_all_q_reference_conditional_target_pilot",
        "authority": f"User-approved Review {review_version} execution window",
        "active_review_sha": review_commit,
        "active_review_path": review_path,
        "active_review_sha256": review_sha256,
        "source_at_entry": source_at_entry,
        "review_at_registration": review_commit,
        "t0_utc": t0_text,
        "numeric_cutoff_utc": cutoff_text,
        "deadline_utc": deadline_text,
        "campaign_seconds": total_seconds,
        "numeric_cutoff_seconds": float(numeric_seconds),
        "closeout_reserve_seconds": closeout_seconds,
        "time_policy": CONSERVATIVE_REALTIME,
        "stage_scope": list(stage_scope),
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
        "bootstrap_time_treatment": "test fixture; immutable T0 and preserved prior costs",
    }
    window_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    window_sha = hashlib.sha256(window_path.read_bytes()).hexdigest()
    contract = {
        "schema": task40_v31_contract.V32_CONTRACT_SCHEMA,
        "status": "USER_APPROVED",
        "service_start_allowed": True,
        "review": {
            "path": review_path,
            "commit": review_commit,
            "sha256": review_sha256,
        },
        "source_freeze": {"source_sha": run_source},
        "user_approval": {
            "approved": True,
            "scope": approval_scope,
            "window_sha256": window_sha,
        },
        "execution": {
            "window": {
                "window_path": str(window_path),
                "window_sha256": window_sha,
                "source_at_entry": source_at_entry,
                "total_seconds": total_seconds,
                "numeric_seconds": numeric_seconds,
                "closeout_seconds": closeout_seconds,
                "t0_utc": t0_text,
                "numeric_cutoff_utc": cutoff_text,
                "deadline_utc": deadline_text,
            },
            "run_source_sha": run_source,
        },
    }
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

    assert source_at_entry != run_source
    assert route["version"] == "V31"  # internal compatibility route
    assert route["review_version"] == review_version
    assert route["stage_scope"] == list(stage_scope)
    assert Path(route["path"]).resolve() == window_path.resolve()
    assert route["sha256"] == window_sha
    assert not (
        tmp_path
        / task40_v31_contract.v31_source_artifact_relative(run_source)
        / f"campaign_window_{review_version.lower()}.json"
    ).exists()


@pytest.mark.parametrize("review_version", ["V32", "V33"])
def test_v32_v33_worker_binding_returns_fixed_q4_template(
    tmp_path, monkeypatch, review_version
):
    from src.runners import task40_v31_contract
    from src.solvers import task40_v30_selected_q_csr
    from src.solvers.task40_v30_qualified_q_csr import (
        make_v31_q_csr_import_authorization,
    )

    contract, binding, payload, environment, contract_sha = _v31_worker_fixture(tmp_path)
    review_path = getattr(task40_v31_contract, f"{review_version}_REVIEW_PATH")
    review_commit = getattr(task40_v31_contract, f"{review_version}_REVIEW_COMMIT")
    review_sha256 = getattr(task40_v31_contract, f"{review_version}_REVIEW_SHA256")
    total_seconds = getattr(task40_v31_contract, f"{review_version}_TOTAL_SECONDS")
    numeric_seconds = getattr(task40_v31_contract, f"{review_version}_NUMERIC_SECONDS")
    closeout_seconds = getattr(task40_v31_contract, f"{review_version}_CLOSEOUT_SECONDS")
    run_source = contract["source_freeze"]["source_sha"]
    source_at_entry = contract["execution"]["window"]["source_at_entry"]
    source_root = tmp_path / V31_ARTIFACT_ROOT_RELATIVE / f"source_{run_source}"
    window_path = (
        tmp_path
        / V31_ARTIFACT_ROOT_RELATIVE
        / f"source_{source_at_entry}"
        / f"campaign_window_{review_version.lower()}.json"
    ).resolve()
    template = task40_v31_contract.v32_q4_pending_import_template(
        execution_root=tmp_path,
        consumer_source_sha=run_source,
    )
    window_sha = "9" * 64
    authorization = task40_v31_contract.bind_v32_q4_pending_import(
        template,
        consumer_execution_identity={"source_sha": run_source, "window_sha256": window_sha},
    )
    complete_template = {
        "schema": task40_v31_contract.V32_Q4_COMPLETE_IMPORT_SCHEMA,
        "q_index": 4,
        "twist_index": 0,
        "profile": V31_PROFILE,
        "shape": [2, 2],
        "operator_identity": {
            "scientific_input_sha256": "1" * 64,
            "profile_identity_sha256": "2" * 64,
            "ordered_mode_sha256": "3" * 64,
            "q_map_sha256": "4" * 64,
            "original_h_sha256": "5" * 64,
        },
        "matrix_source_identity": {
            "source_sha": "a" * 40,
            "window_sha256": "b" * 64,
        },
        "producer_identity": {"kind": "small-q4-fixture"},
        "producer_execution_identity": {
            "source_sha": "c" * 40,
            "window_sha256": "d" * 64,
        },
        "native_execution_identity": {
            "source_sha": "c" * 40,
            "window_sha256": "d" * 64,
        },
        "csr_manifest": {"path": str(tmp_path / "q4_manifest.json"), "sha256": "6" * 64},
        "native_qualification": {
            "path": str(tmp_path / "q4_native.json"),
            "sha256": "7" * 64,
            "status": "PASS",
        },
        "csr_artifacts": {
            name: {"path": str(tmp_path / f"q4_{name}.npy"), "bytes": 1, "sha256": f"{index:x}" * 64}
            for index, name in enumerate(("data", "indices", "indptr"), start=8)
        },
    }
    complete_authorization = make_v31_q_csr_import_authorization(
        q_index=4,
        twist_index=0,
        profile=V31_PROFILE,
        operator_identity=complete_template["operator_identity"],
        matrix_source_identity=complete_template["matrix_source_identity"],
        producer_identity=complete_template["producer_identity"],
        producer_execution_identity=complete_template["producer_execution_identity"],
        native_execution_identity=complete_template["native_execution_identity"],
        csr_manifest_sha256=complete_template["csr_manifest"]["sha256"],
        native_qualification_sha256=complete_template["native_qualification"]["sha256"],
        csr_artifacts=complete_template["csr_artifacts"],
        consumer_execution_identity={"source_sha": run_source, "window_sha256": window_sha},
    )
    imports = {
        "complete": {"4": complete_authorization},
        "numeric_pending": {"4": authorization},
    }
    contract["schema"] = task40_v31_contract.V32_CONTRACT_SCHEMA
    contract["review"] = {
        "path": review_path,
        "commit": review_commit,
        "sha256": review_sha256,
    }
    contract["preparation"]["q4_numeric_pending_import"] = template
    contract["preparation"]["q4_complete_import"] = complete_template
    contract["execution"]["window"].update(
        {
            "window_path": str(window_path),
            "window_sha256": window_sha,
            "total_seconds": total_seconds,
            "numeric_seconds": numeric_seconds,
            "closeout_seconds": closeout_seconds,
        }
    )
    contract["execution"]["campaign_window_path"] = str(window_path)
    contract["execution"]["campaign_window_sha256"] = window_sha
    contract["execution"]["q_csr_import_authorizations"] = imports
    contract_path = source_root / f"execution_contract_{review_version.lower()}.approved.json"
    binding["contract_path"] = str(contract_path.resolve())
    binding["contract_sha256"] = contract_sha
    binding["execution_window_path"] = str(window_path)
    binding["execution_window_sha256"] = window_sha
    binding["q_csr_import_authorizations"] = imports
    payload["execution"]["task40_v31_q_csr_import_authorizations"] = {
        "complete": {"4": complete_template},
        "numeric_pending": {"4": template}
    }
    environment["TASK40_V31_EXECUTION_WINDOW_PATH"] = str(window_path)
    environment["TASK40_V31_EXECUTION_WINDOW_SHA256"] = window_sha

    preflight_calls = []
    monkeypatch.setattr(
        task40_v30_selected_q_csr,
        "preflight_v32_q4_numeric_pending_import",
        lambda auth, **kwargs: preflight_calls.append((dict(auth), kwargs)),
    )
    monkeypatch.setattr(
        task40_v31_contract,
        "v32_q4_complete_import_template",
        lambda **_kwargs: complete_template,
    )

    # Model the original approved window's pre-COMPLETE route with a tracked
    # fixture. Its imported authorization remains numeric-pending only; the
    # new same-window package adds a separate COMPLETE authorization.
    old_contract = {
        "execution": {"q_csr_import_authorizations": {"numeric_pending": {"4": authorization}}},
        "preparation": {"q4_numeric_pending_import": template},
    }
    old_imports = old_contract["execution"]["q_csr_import_authorizations"]
    assert set(old_imports) == {"numeric_pending"}
    assert old_contract["preparation"]["q4_numeric_pending_import"] == template

    repository_root = Path(__file__).resolve().parents[2]
    from src.runners.task40_v30_contract import (
        V30_CANONICAL_INPUT_RELATIVE,
    )
    staged_text = task40_v31_contract._render_v31_stage_input(
        (repository_root / V30_CANONICAL_INPUT_RELATIVE).read_text(encoding="utf-8"),
        selector_relative_path="source-fixture/q_csr_selector_v31.json",
        selector_sha256="e" * 64,
        factor_relative_path="source-fixture/factor_bank",
        q4_numeric_pending_import=template,
        q4_complete_import=complete_template,
    )
    import tomllib

    staged_route = tomllib.loads(staged_text)["execution"][
        "task40_v31_q_csr_import_authorizations"
    ]
    assert staged_route == {
        "complete": {"4": complete_template},
        "numeric_pending": {"4": template},
    }
    worker = task40_v31_contract.validate_v31_worker_execution_binding(
        binding,
        contract=contract,
        contract_sha256=contract_sha,
        resolved_payload=payload,
        source_sha=run_source,
        environment=environment,
        repo_root=tmp_path,
    )

    assert worker["review_version"] == review_version
    assert worker["q4_numeric_pending_import_template"] == template
    assert worker["q4_numeric_pending_import_authorization"] == authorization
    assert worker["q4_complete_import_template"] == complete_template
    assert worker["q4_complete_import_authorization"] == complete_authorization
    assert preflight_calls == [
        (
            authorization,
            {
                "profile": V31_PROFILE,
                "execution_identity": {"source_sha": run_source, "window_sha256": window_sha},
                "output_directory": template["consumer_output_root"],
            },
        )
    ]


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
        "schema": "task40extra.review_v31_execution_contract.v1",
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

    payload["execution"].pop("task40_v30_q_csr_binding")
    payload["execution"]["task40_v31_q_csr_import_authorizations"] = {}
    with pytest.raises(ValueError, match="q4 import differs from its frozen execution contract"):
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
    from types import SimpleNamespace

    from benchmarks import subreaper_watchdog as watchdog
    from scripts import task40_v20_service_workflow as service
    from src.runners import task40_v30_contract, task40_v31_contract

    root = tmp_path / "repo"
    evidence = root / "benchmarks/artifacts/run-evidence"
    evidence.mkdir(parents=True)
    run_directory = root / "results" / "v31-attempt"
    run_directory.mkdir(parents=True)
    source_sha = "b" * 40
    input_path = (
        root
        / V31_ARTIFACT_ROOT_RELATIVE
        / f"source_{source_sha}"
        / "stage_inputs/full/target_original_ny8_resource_pilot_v20.dat"
    )
    input_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
    input_path.write_text(
        f'run_id = "{run_id}"\n[solver]\npreconditioner = "{V31_PROFILE}"\n',
        encoding="utf-8",
    )
    numerical_path = run_directory / "numerical-output"
    summary_path = run_directory / "run_summary.json"
    manifest_path = run_directory / "run_manifest.json"
    input_sha = service._sha256_file(input_path)
    window_path = root / "campaign_window_v31.json"
    window_path.write_text(
        json.dumps(
            {
                "campaign_seconds": task40_v31_contract.V31_TOTAL_SECONDS,
                "numeric_cutoff_seconds": task40_v31_contract.V31_NUMERIC_SECONDS,
                "closeout_reserve_seconds": task40_v31_contract.V31_CLOSEOUT_SECONDS,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
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
                "output_directory": str(run_directory),
                "numerical_output_directory": str(numerical_path),
                "task40_v20_campaign": {
                    "path": str(window_path),
                    "sha256": window_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "status": "finished",
                "result_classification": "WORKER_FAILED",
                "exit_status": 4,
                "run_id": run_id,
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "input_path": str(input_path),
                "output_directory": str(run_directory),
                "numerical_output_directory": str(numerical_path),
                "task40_v20_campaign": {
                    "window_path": str(window_path),
                    "window_sha256": window_sha,
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = Path(sys.executable).resolve().parent.parent
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

    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: root))

    def fake_git(command, **_kwargs):
        if command[:2] == ["git", "rev-parse"]:
            output = source_sha
        elif command[:3] == ["git", "branch", "--show-current"]:
            output = source_state["branch"]
        elif command[:2] == ["git", "status"]:
            output = ""
        else:
            raise AssertionError(f"unexpected subprocess command: {command!r}")
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(watchdog.subprocess, "run", fake_git)
    worker_environment = {
        "TASK40_V31_STRICT_EXECUTION": "1",
        "TASK40_V31_CONTRACT_SHA256": "d" * 64,
        "TASK40_V31_CONTRACT_PATH": str(root / "approved-contract.json"),
    }
    campaign = SimpleNamespace(sha256=window_sha, path=window_path)
    validated = watchdog._validate_campaign_closeout_authorization(
        command=command,
        campaign=campaign,
        authorization=authorization,
        worker_environment=worker_environment,
    )
    assert validated == authorization

    bad_source_authorization = dict(authorization, source_sha="c" * 40)
    with pytest.raises(ValueError, match="not bound to a V31 worker failure"):
        watchdog._validate_campaign_closeout_authorization(
            command=command,
            campaign=campaign,
            authorization=bad_source_authorization,
            worker_environment=worker_environment,
        )
    bad_hash_authorization = dict(authorization)
    bad_hash_authorization["input_sha256s"] = list(authorization["input_sha256s"])
    bad_hash_authorization["input_sha256s"][1] = "0" * 64
    with pytest.raises(ValueError, match="input hash changed"):
        watchdog._validate_campaign_closeout_authorization(
            command=command,
            campaign=campaign,
            authorization=bad_hash_authorization,
            worker_environment=worker_environment,
        )

    v30_contract = {
        "execution": {
            "campaign_window_path": str(window_path),
            "campaign_window_sha256": window_sha,
        }
    }
    monkeypatch.setattr(
        task40_v30_contract,
        "require_authorized_contract",
        lambda *_args, **_kwargs: (v30_contract, "d" * 64),
    )
    v30_authorization = dict(authorization)
    v30_authorization["schema"] = "task40extra.review_v31_closeout_checker_authorization.v1"
    v30_authorization["v30_contract_sha256"] = v30_authorization.pop("v31_contract_sha256")
    with pytest.raises(ValueError, match="numerical output directory is missing"):
        watchdog._validate_campaign_closeout_authorization(
            command=command,
            campaign=campaign,
            authorization=v30_authorization,
            worker_environment={
                "TASK40_V30_STRICT_EXECUTION": "1",
                "TASK40_V30_CONTRACT_SHA256": "d" * 64,
                "TASK40_V30_CONTRACT_PATH": str(root / "approved-v30-contract.json"),
            },
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["source_sha"] = "c" * 40
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
    summary.pop("source_sha")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
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


@pytest.mark.parametrize(
    "partial_footer",
    (False, True),
    ids=("missing-footer", "valid-partial"),
)
def test_v32_service_supervisor_runs_real_watchdog_and_check_partial(
    tmp_path, monkeypatch, partial_footer
):
    import subprocess

    from scripts import task40_v20_service_workflow as service
    from src.runners import task40_v10_campaign, task40_v31_contract
    from src.runners.workflow_timebase import clock_sample

    source_repo = Path(service.__file__).resolve().parents[1]
    from src.runners.task40_v30_contract import V30_CANONICAL_INPUT_RELATIVE

    repo_root = tmp_path / "fixture_repo"
    repo_root.mkdir()
    (repo_root / ".gitignore").write_text(
        "results/\nbenchmarks/artifacts/\n"
        f"{V30_CANONICAL_INPUT_RELATIVE.as_posix()}\n",
        encoding="utf-8",
    )
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir()
    wrapper = scripts_dir / "task40_v20_service_workflow.py"
    wrapper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(source_repo)!r})\n"
        "from scripts.task40_v20_service_workflow import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    def git(*args):
        subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True)

    git("init", "--quiet", "--initial-branch=task40extra_0p7nm_engineering")
    git("config", "user.name", "Task40 fixture")
    git("config", "user.email", "task40-fixture@example.invalid")
    git("add", ".gitignore", "scripts/task40_v20_service_workflow.py")
    git("commit", "--quiet", "-m", "test fixture")
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
    ).strip()
    assert subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repo_root, text=True
    ) == ""

    source_root = repo_root / V31_ARTIFACT_ROOT_RELATIVE / f"source_{source_sha}"
    entry_root = repo_root / V31_ARTIFACT_ROOT_RELATIVE / f"source_{'c' * 40}"
    contract_path = source_root / "execution_contract_v32.approved.json"
    window_path = entry_root / "campaign_window_v32.json"
    canonical_path = repo_root / V30_CANONICAL_INPUT_RELATIVE
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_source = source_repo / V30_CANONICAL_INPUT_RELATIVE
    canonical_path.write_bytes(canonical_source.read_bytes())
    input_path = source_root / "stage_inputs" / "full" / V30_CANONICAL_INPUT_RELATIVE.name
    input_path.parent.mkdir(parents=True, exist_ok=True)
    selector_path = source_root / "q_csr_selector_v31.json"
    selector_path.write_text(json.dumps({"schema": "test.v32.selector.v1"}) + "\n", encoding="utf-8")
    selector_sha = hashlib.sha256(selector_path.read_bytes()).hexdigest()
    q4_template = task40_v31_contract.v32_q4_pending_import_template(
        execution_root=repo_root,
        consumer_source_sha=source_sha,
    )
    staged_text = task40_v31_contract._render_v31_stage_input(
        canonical_path.read_text(encoding="utf-8"),
        selector_relative_path=(
            task40_v31_contract.v31_source_artifact_relative(source_sha)
            / "q_csr_selector_v31.json"
        ).as_posix(),
        selector_sha256=selector_sha,
        factor_relative_path=(
            task40_v31_contract.v31_source_artifact_relative(source_sha)
            / "factor_bank"
        ).as_posix(),
        q4_numeric_pending_import=q4_template,
    )
    input_path.write_text(staged_text, encoding="utf-8")

    anchor = clock_sample(include_boot_id=True)
    elapsed_before_fixture = float(task40_v31_contract.V32_NUMERIC_SECONDS) + 5.0
    anchor["utc_ns"] = int(anchor["utc_ns"]) - int(elapsed_before_fixture * 1e9)
    anchor["monotonic"] = float(anchor["monotonic"]) - elapsed_before_fixture
    anchor["boottime"] = float(anchor["boottime"]) - elapsed_before_fixture

    def utc_iso(timestamp_ns):
        seconds, nanos = divmod(int(timestamp_ns), 1_000_000_000)
        stamp = dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        return f"{stamp}.{nanos:09d}Z"

    t0_ns = int(anchor["utc_ns"])
    window_payload = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign": task40_v31_contract.V32_REGISTRATION_SCHEMA,
        "authority": "test-only V32 supervised no-footer fixture",
        "active_review_sha": task40_v31_contract.V32_REVIEW_COMMIT,
        "active_review_path": task40_v31_contract.V32_REVIEW_PATH,
        "active_review_sha256": task40_v31_contract.V32_REVIEW_SHA256,
        "source_at_entry": "c" * 40,
        "review_at_registration": task40_v31_contract.V32_REVIEW_COMMIT,
        "t0_utc": utc_iso(t0_ns),
        "numeric_cutoff_utc": utc_iso(t0_ns + 85_200_000_000_000),
        "deadline_utc": utc_iso(t0_ns + 86_400_000_000_000),
        "campaign_seconds": task40_v31_contract.V32_TOTAL_SECONDS,
        "numeric_cutoff_seconds": task40_v31_contract.V32_NUMERIC_SECONDS,
        "closeout_reserve_seconds": task40_v31_contract.V32_CLOSEOUT_SECONDS,
        "time_policy": task40_v10_campaign.CONSERVATIVE_REALTIME,
        "stage_scope": list(task40_v31_contract.V32_STAGE_SCOPE),
        "forbidden_scope": ["window_refresh", "resource_increase", "unrelated_mutation"],
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "bootstrap_boottime_elapsed_seconds": None,
        "bootstrap_utc_elapsed_seconds": 0.0,
        "bootstrap_time_treatment": "test fixture T0 equals initial sample",
        "initial_boot_id": anchor["boot_id"],
        "first_full_three_clock_sample": dict(anchor),
    }
    window_bytes = (json.dumps(window_payload, sort_keys=True) + "\n").encode()
    window_path.parent.mkdir(parents=True, exist_ok=True)
    window_path.write_bytes(window_bytes)
    window_sha = hashlib.sha256(window_bytes).hexdigest()
    q4_authorization = task40_v31_contract.bind_v32_q4_pending_import(
        q4_template,
        consumer_execution_identity={
            "source_sha": source_sha,
            "window_sha256": window_sha,
        },
    )
    input_identity = task40_v31_contract.require_v31_input_identity(
        canonical_path,
        input_path,
        repo_root=repo_root,
        source_sha=source_sha,
        selector_sha256=selector_sha,
        q4_numeric_pending_import=q4_template,
    )
    campaign_accounting = window_path.with_name("campaign_accounting_v10.jsonl")
    campaign_accounting.write_text("", encoding="utf-8")

    contract = {
        "schema": task40_v31_contract.V32_CONTRACT_SCHEMA,
        "status": "USER_APPROVED",
        "review": {
            "path": task40_v31_contract.V32_REVIEW_PATH,
            "commit": task40_v31_contract.V32_REVIEW_COMMIT,
            "sha256": task40_v31_contract.V32_REVIEW_SHA256,
        },
        "source_freeze": {
            "required": True,
            "source_sha": source_sha,
            "branch": task40_v31_contract.V31_BRANCH,
            "clean": True,
        },
        "preparation": {"q4_numeric_pending_import": q4_template},
        "execution": {
            "root": str(repo_root),
            "profile": V31_PROFILE,
            "resources": dict(V31_RESOURCES),
            "jit_cache": str(repo_root / "benchmarks/artifacts/test_jit_cache"),
            "window": {
                "window_path": str(window_path),
                "window_sha256": window_sha,
                "total_seconds": task40_v31_contract.V32_TOTAL_SECONDS,
                "numeric_seconds": task40_v31_contract.V32_NUMERIC_SECONDS,
                "closeout_seconds": task40_v31_contract.V32_CLOSEOUT_SECONDS,
                "source_at_entry": "c" * 40,
            },
            "campaign_window_path": str(window_path),
            "campaign_window_sha256": window_sha,
            "run_source_sha": source_sha,
            "input_path": str(input_path),
            "selector_path": str(source_root / "q_csr_selector_v31.json"),
            "q_csr_import_authorizations": {
                "numeric_pending": {"4": q4_authorization}
            },
        },
    }
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    bootstrap_dir = tmp_path / "bootstrap"
    bootstrap_dir.mkdir()
    (bootstrap_dir / "sitecustomize.py").write_text(
        """
import hashlib
import json
import os
from pathlib import Path
from src.runners import task40_v10_campaign, task40_v31_contract
from scripts import task40_v20_service_workflow as service
from src.solvers import task40_v22_operator_probe
from benchmarks import subreaper_watchdog

root = Path(os.environ["TASK40_TEST_REPO_ROOT"]).resolve()
contract_path = Path(os.environ["TASK40_TEST_V31_CONTRACT_PATH"]).resolve()
contract_sha = os.environ["TASK40_TEST_V31_CONTRACT_SHA256"]

def require_fixture_contract(path, expected_sha256=None, current_root=None):
    path = Path(path).resolve()
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if path != contract_path or digest != contract_sha or (expected_sha256 and digest != expected_sha256):
        raise ValueError("test fixture contract identity changed")
    return json.loads(raw), digest

task40_v31_contract.require_v31_execution_contract = require_fixture_contract
service.ROOT = root
task40_v10_campaign.__file__ = str(root / "src/runners/task40_v10_campaign.py")
task40_v10_campaign._validate_v31_campaign_registration = lambda *_args, **_kwargs: None
task40_v22_operator_probe._resource_admission = lambda *_args, **_kwargs: {
    "current_process_cgroup": {
        "dedicated_job_cgroup": True,
        "memory_limit_bytes": 1649267441664,
        "memory_current_bytes": 1024,
        "swap_current_bytes": 0,
    },
    "host_effective_available_bytes": 68719476736,
}
subreaper_watchdog.cgroup_snapshot = lambda *_args, **_kwargs: {
    "dedicated_job_cgroup": True,
    "readable": True,
    "memory_limit_bytes": 1649267441664,
    "memory_current_bytes": 1024,
    "swap_current_bytes": 0,
}
subreaper_watchdog.memory_envelope = lambda *_args, **_kwargs: {
    "launch_cap_bytes": 1 << 40,
    "effective_available_bytes": 1 << 40,
    "effective_available_after_reserves_bytes": 1 << 40,
    "reserve_bytes": 0,
    "reserve_domains_separated": True,
}
""",
        encoding="utf-8",
    )

    original_require = task40_v31_contract.require_v31_execution_contract

    def require_parent_fixture_contract(path, expected_sha256=None, current_root=None):
        raw = Path(path).resolve().read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != contract_sha or (expected_sha256 and digest != expected_sha256):
            raise ValueError("test fixture contract identity changed")
        return json.loads(raw), digest

    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_execution_contract",
        require_parent_fixture_contract,
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "__file__",
        str(repo_root / "src/runners/task40_v10_campaign.py"),
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "_validate_v31_campaign_registration",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "_v31_live_resource_gate",
        lambda *_args, **_kwargs: {"passed": True, "fixture": "host resource sample injected"},
    )

    run_id = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
    run_directory = repo_root / "results" / run_id
    numerical_output = run_directory / "numerical_output"
    numerical_output.mkdir(parents=True)
    summary_path = run_directory / "run_summary.json"
    manifest_path = run_directory / "run_manifest.json"
    campaign_identity = {
        "window_path": str(window_path),
        "window_sha256": window_sha,
        "accounting_path": str(campaign_accounting),
    }
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "finished",
                "result_classification": (
                    "RESOURCE_CONTROLLED_STOP" if partial_footer else "TEST_FIXTURE_NO_FOOTER"
                ),
                "output_directory": str(run_directory),
                "numerical_output_directory": str(numerical_output),
                "task40_v20_campaign": campaign_identity,
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "source_sha": source_sha,
                "input_path": str(input_path),
                "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "physical_model_sha256": "d" * 64,
                "mesh_id": "TARGET_ORIGINAL_NY8",
                "output_directory": str(run_directory),
                "numerical_output_directory": str(numerical_output),
                "scientific_input_sha256": input_identity["scientific_input_sha256"],
                "v31_input_identity": input_identity,
                "v31_execution_contract_binding": {
                    "review_version": "V32",
                    "contract_path": str(contract_path),
                    "contract_sha256": contract_sha,
                    "run_source_sha": source_sha,
                    "execution_window_sha256": window_sha,
                    "selector_path": str(selector_path.resolve()),
                    "selector_sha256": selector_sha,
                    "input_identity": input_identity,
                    "q4_numeric_pending_import_template": q4_template,
                    "q4_numeric_pending_import_authorization": q4_authorization,
                },
                "solver": {"preconditioner": V31_PROFILE},
                "task40_v20_campaign": campaign_identity,
            }
        ),
        encoding="utf-8",
    )
    if partial_footer:
        (numerical_output / "v20_partial_result.json").write_text(
            json.dumps(
                {
                    "schema": "task40extra.review_v20_partial_result.v2",
                    "status": "controlled_stop",
                    "outcome": "RESOURCE_CONTROLLED_STOP",
                    "run_id": run_id,
                    "source_sha": source_sha,
                    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                    "physical_model_sha256": "d" * 64,
                    "requested_stop_stage": "full",
                    "attempted_stages": ["preflight", "full"],
                    "completed_stages": ["preflight"],
                    "official_result": False,
                    "resource_gate": {
                        "stage": "full",
                        "passed": False,
                        "fixture_only": True,
                    },
                    "q_coverage": {
                        "status": "UNKNOWN",
                        "expected_q_count": 8,
                        "built_q_count": 0,
                    },
                    "cleanup": {
                        "status": "PASS",
                        "native_owners_released": True,
                        "process_descendants_cleared": True,
                        "temporary_stage_objects_released": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        (numerical_output / "task40_v10_p6_candidate_summary.json").write_text(
            json.dumps({"status": "CONTROLLED_STOP", "official_result": False}),
            encoding="utf-8",
        )

    runtime_prefix = Path(sys.prefix).resolve()
    evidence = repo_root / "benchmarks/artifacts/test_supervision"
    evidence.mkdir(parents=True)
    checker_output = evidence / "partial_checker_result.json"
    command = [
        str(runtime_prefix / "bin/python"),
        "scripts/task40_v20_service_workflow.py",
        "check-partial",
        "--input", str(input_path),
        "--summary", str(summary_path),
        "--manifest", str(manifest_path),
        "--numerical-output", str(numerical_output),
        "--stop-stage", "full",
        "--output", str(checker_output),
    ]
    marker_environment = {
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_QUALIFICATION_SCOPE": "imports_only_C1_FE_JIT_NOT_RUN",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": "e" * 64,
        "TASK40_V31_STRICT_EXECUTION": "1",
        "TASK40_V31_CONTRACT_PATH": str(contract_path),
        "TASK40_V31_CONTRACT_SHA256": contract_sha,
        "TASK40_V31_EXECUTION_WINDOW_PATH": str(window_path),
        "TASK40_V31_EXECUTION_WINDOW_SHA256": window_sha,
        "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(V31_RESOURCES["task_memory_max_bytes"]),
        "TASK40_V31_HOST_RESERVE_BYTES": str(V31_RESOURCES["host_reserve_bytes"]),
        "TASK40_V31_MEMORY_SWAP_MAX_BYTES": "0",
        "TASK40_TEST_REPO_ROOT": str(repo_root),
        "TASK40_TEST_V31_CONTRACT_PATH": str(contract_path),
        "TASK40_TEST_V31_CONTRACT_SHA256": contract_sha,
        "PYTHONPATH": os.pathsep.join(
            (str(bootstrap_dir), str(source_repo), os.environ.get("PYTHONPATH", ""))
        ),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    assert subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repo_root,
        text=True,
    ) == ""
    environment = dict(os.environ)
    environment.update(marker_environment)
    source_state = {
        "branch": task40_v31_contract.V31_BRANCH,
        "source_sha": source_sha,
        "clean": True,
    }
    events = []
    event_log = evidence / "outer_events.jsonl"
    event_identity = {"fixture": "V32 real service-supervisor path; no FE/PDE"}
    result = service._supervise_required_checker(
        command=command,
        checker_kind="task40_v20_partial_receipt_checker",
        evidence_directory=evidence,
        runtime_prefix=runtime_prefix,
        environment=environment,
        repo_root=repo_root,
        campaign_window=window_path,
        campaign_sha256=window_sha,
        campaign_accounting=campaign_accounting,
        source_state=source_state,
        profile=V31_PROFILE,
        events=events,
        event_log=event_log,
        event_identity=event_identity,
    )

    checker_code, checker_payload, details = result
    assert checker_code == (0 if partial_footer else 2)
    assert checker_payload is not None
    assert checker_payload["status"] == (
        "PARTIAL_RECEIPT_CHECKED" if partial_footer else "NO_PARTIAL_FOOTER"
    )
    assert checker_payload["official_result"] is False
    if partial_footer:
        assert checker_payload["checker_passed"] is True, checker_payload["errors"]
        assert checker_payload["v31_reference_audit_status"] == "NOT_RUN_REFERENCE_NOT_COMPLETE"
    assert checker_output.is_file()
    assert json.loads(checker_output.read_text(encoding="utf-8"))["status"] == checker_payload["status"]
    assert details["qualified_supervisor"]["returncode"] == 0
    assert Path(details["watchdog_summary_path"]).is_file()
    watchdog_summary = json.loads(Path(details["watchdog_summary_path"]).read_text(encoding="utf-8"))
    assert watchdog_summary["descendants_cleared"] is True
    campaign_summary = watchdog_summary["task40_v10_campaign"]
    assert campaign_summary["campaign_seconds"] == task40_v31_contract.V32_TOTAL_SECONDS
    assert campaign_summary["numerical_cutoff_seconds"] == task40_v31_contract.V32_NUMERIC_SECONDS
    assert campaign_summary["closeout_reserve_seconds"] == task40_v31_contract.V32_CLOSEOUT_SECONDS
    assert campaign_summary["phase"] == "closeout"
    assert 0.0 < campaign_summary["phase_sub_budget_seconds"] <= task40_v31_contract.V32_CLOSEOUT_SECONDS
    closeout_sample = campaign_summary["watchdog_end_accounting"]
    assert closeout_sample["phase"] == "closeout"
    assert (
        task40_v31_contract.V32_NUMERIC_SECONDS
        <= closeout_sample["cumulative_charged_seconds"]
        < task40_v31_contract.V32_TOTAL_SECONDS
    )
    assert (numerical_output / "v20_partial_result.json").exists() is partial_footer
    assert original_require is not None

    import shutil

    receipt_label = "valid-partial" if partial_footer else "missing-footer"
    receipt_root = (
        source_repo
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v32_preparation"
        / "supervised_partial_receipts"
        / receipt_label
    )
    receipt_root.mkdir(parents=True, exist_ok=True)
    preserved = {
        "checker_result.json": checker_output,
        "supervision_request.json": evidence / "required_checker_supervision_request.json",
        "supervision_response.json": evidence / "required_checker_supervision_response.json",
        "supervisor_stdout.raw.txt": evidence / "required_checker_supervisor_stdout.raw.txt",
        "supervisor_stderr.raw.txt": evidence / "required_checker_supervisor_stderr.raw.txt",
        "outer_events.jsonl": event_log,
        "watchdog_summary.json": Path(details["watchdog_summary_path"]),
        "run_summary.json": summary_path,
        "run_manifest.json": manifest_path,
        "execution_contract_v32.approved.json": contract_path,
        "campaign_window_v32.json": window_path,
        "staged_input.dat": input_path,
        "q_csr_selector_v31.json": selector_path,
    }
    if partial_footer:
        preserved["v20_partial_result.json"] = numerical_output / "v20_partial_result.json"
        preserved["task40_v10_p6_candidate_summary.json"] = (
            numerical_output / "task40_v10_p6_candidate_summary.json"
        )
    for name, source in preserved.items():
        assert source.is_file(), source
        shutil.copyfile(source, receipt_root / name)


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


def test_v32_campaign_phase_budget_enters_closeout_at_85200_and_expires_at_86400(tmp_path):
    from src.runners.task40_v10_campaign import FixedCampaignWindow
    from src.runners.task40_v31_contract import (
        V32_CLOSEOUT_SECONDS,
        V32_NUMERIC_SECONDS,
        V32_TOTAL_SECONDS,
    )

    t0_ns = 1_800_000_000_000_000_000
    window = FixedCampaignWindow(
        path=tmp_path / "campaign_window_v32.json",
        sha256="a" * 64,
        payload={"review": "V32 fixture; budget arithmetic only"},
        anchor={
            "monotonic": 100.0,
            "boottime": 100.0,
            "utc_ns": t0_ns,
            "boot_id": "test-boot",
        },
        t0_utc_ns=t0_ns,
        deadline_utc_ns=t0_ns + V32_TOTAL_SECONDS * 1_000_000_000,
        total_seconds=float(V32_TOTAL_SECONDS),
        bootstrap_seconds=0.0,
        closeout_seconds=float(V32_CLOSEOUT_SECONDS),
    )
    cutoff_ns = t0_ns + V32_NUMERIC_SECONDS * 1_000_000_000

    assert window.cutoff_seconds == V32_NUMERIC_SECONDS
    assert window.remaining_seconds(
        phase="numeric",
        cumulative_charged_seconds=float(V32_NUMERIC_SECONDS),
        now_utc_ns=cutoff_ns,
    ) == 0.0
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=float(V32_NUMERIC_SECONDS),
        now_utc_ns=cutoff_ns,
    ) == float(V32_CLOSEOUT_SECONDS)
    assert window.phase_expired(
        phase="numeric",
        cumulative_charged_seconds=float(V32_NUMERIC_SECONDS),
        now_utc_ns=cutoff_ns,
    ) is True
    assert window.phase_expired(
        phase="closeout",
        cumulative_charged_seconds=float(V32_NUMERIC_SECONDS),
        now_utc_ns=cutoff_ns,
    ) is False
    after_cutoff_ns = cutoff_ns + 5_000_000_000
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=float(V32_NUMERIC_SECONDS) + 5.0,
        now_utc_ns=after_cutoff_ns,
        termination_reserve_seconds=60.0,
    ) == float(V32_CLOSEOUT_SECONDS) - 65.0
    deadline_ns = t0_ns + V32_TOTAL_SECONDS * 1_000_000_000
    assert window.remaining_seconds(
        phase="closeout",
        cumulative_charged_seconds=float(V32_TOTAL_SECONDS),
        now_utc_ns=deadline_ns,
    ) == 0.0
    assert window.phase_expired(
        phase="closeout",
        cumulative_charged_seconds=float(V32_TOTAL_SECONDS),
        now_utc_ns=deadline_ns,
    ) is True


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



@pytest.mark.parametrize(
    ("leader_exit_code", "kill_sent", "expected_bound"),
    [(-9, True, True), (-15, False, True), (0, False, True), (1, False, False)],
)
def test_v31_partial_checker_accepts_only_bound_campaign_cutoff_fixture(
    tmp_path, monkeypatch, leader_exit_code, kill_sent, expected_bound
):
    fixture_path = Path(__file__).parent / "fixtures" / "task40_v31_cutoff_watchdog.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    watchdog = fixture["watchdog"]
    watchdog["leader_exit_code"] = leader_exit_code
    if not kill_sent:
        watchdog.pop("first_SIGKILL", None)
    source_sha = fixture["provenance"]["source_sha"]
    watchdog_campaign = watchdog["task40_v10_campaign"]

    root = tmp_path / "repo"
    run_directory = root / "results" / "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"
    run_directory.mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "task40_v20_service_workflow.py").write_text("# fixture\n")
    evidence = root / "artifacts" / "service_run"
    evidence.mkdir(parents=True)
    input_path = root / "stage_inputs" / "full" / "case.toml"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        f'run_id = "task40extra_0p7nm_target_original_ny8_resource_pilot_v20"\n'
        f'[solver]\npreconditioner = "{V31_PROFILE}"\n',
        encoding="utf-8",
    )
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    summary_path = run_directory / "run_summary.json"
    manifest_path = run_directory / "run_manifest.json"
    numerical_path = run_directory / "numerical_output"
    window_path = root / "artifacts" / "campaign_window_v31.json"
    window_payload = {
        "campaign_seconds": watchdog_campaign["campaign_seconds"],
        "numeric_cutoff_seconds": watchdog_campaign["numerical_cutoff_seconds"],
        "closeout_reserve_seconds": (
            watchdog_campaign["campaign_seconds"]
            - watchdog_campaign["numerical_cutoff_seconds"]
        ),
    }
    window_bytes = (json.dumps(window_payload, sort_keys=True) + "\n").encode("utf-8")
    window_path.write_bytes(window_bytes)
    campaign_sha256 = hashlib.sha256(window_bytes).hexdigest()
    watchdog_campaign["window_sha256"] = campaign_sha256
    watchdog_campaign["watchdog_end_accounting"]["campaign_window_sha256"] = campaign_sha256
    watchdog_path = run_directory / "watchdog" / "summary.json"
    watchdog_path.parent.mkdir()

    # Bind the temporary window bytes and their exact digest through the
    # summary, manifest, watchdog, and accounting tail.
    watchdog_path.write_text(json.dumps(watchdog), encoding="utf-8")

    campaign = {"window_path": str(window_path), "window_sha256": campaign_sha256}
    summary = {
        "status": "finished",
        "result_classification": "PERFORMANCE_CONTROLLED_STOP",
        "exit_status": leader_exit_code,
        "full_workflow_time_exceeded": True,
        "run_id": "task40extra_0p7nm_target_original_ny8_resource_pilot_v20",
        "output_directory": str(run_directory),
        "numerical_output_directory": str(numerical_path),
        "task40_v20_campaign": campaign,
        "resource_authority": watchdog,
    }
    manifest = {
        "status": "finished",
        "result_classification": "PERFORMANCE_CONTROLLED_STOP",
        "exit_status": leader_exit_code,
        "run_id": summary["run_id"],
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "input_path": str(input_path),
        "output_directory": str(run_directory),
        "numerical_output_directory": str(numerical_path),
        "task40_v20_campaign": campaign,
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert not numerical_path.exists()

    is_bound = _v31_missing_numerical_output_is_bound_worker_failure(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_path=numerical_path,
        repo_root=root,
        source_sha=source_sha,
        campaign_sha256=campaign_sha256,
        campaign_window_path=window_path,
    )
    assert is_bound is expected_bound

    checker_command = [
        str(tmp_path / "runtime" / "bin" / "python"),
        "scripts/task40_v20_service_workflow.py",
        "check-partial",
        "--input", str(input_path),
        "--summary", str(summary_path),
        "--manifest", str(manifest_path),
        "--numerical-output", str(numerical_path),
        "--stop-stage", "full",
        "--output", str(evidence / "partial_checker_result.json"),
    ]
    if expected_bound:
        authorization = _task40_v30_closeout_checker_authorization(
            command=checker_command,
            checker_kind="task40_v20_partial_receipt_checker",
            runtime_prefix=tmp_path / "runtime",
            repo_root=root,
            evidence_directory=evidence,
            campaign_sha256=campaign_sha256,
            contract_sha256="c" * 64,
            source_state={"source_sha": source_sha, "clean": True},
            profile=V30_PROFILE,
            allow_missing_numerical_output_for_v31_worker_failure=True,
            expected_campaign_window_path=window_path,
        )
        assert authorization["input_paths"] == [
            str(input_path.resolve()),
            str(summary_path.resolve()),
            str(manifest_path.resolve()),
        ]
        bad_signal_watchdog = dict(watchdog)
        bad_signal_watchdog["first_SIGTERM"] = {
            **dict(watchdog["first_SIGTERM"]),
            "monotonic": watchdog["stop_event"]["monotonic"] - 1.0,
        }
        watchdog_path.write_text(json.dumps(bad_signal_watchdog), encoding="utf-8")
        summary["resource_authority"] = bad_signal_watchdog
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        assert not _v31_missing_numerical_output_is_bound_worker_failure(
            input_path=input_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
            numerical_path=numerical_path,
            repo_root=root,
            source_sha=source_sha,
            campaign_sha256=campaign_sha256,
            campaign_window_path=window_path,
        )
        watchdog_path.write_text(json.dumps(watchdog), encoding="utf-8")
        summary["resource_authority"] = watchdog
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
    else:
        with pytest.raises(ValueError, match="paths are not bound"):
            _task40_v30_closeout_checker_authorization(
                command=checker_command,
                checker_kind="task40_v20_partial_receipt_checker",
                runtime_prefix=tmp_path / "runtime",
                repo_root=root,
                evidence_directory=evidence,
                campaign_sha256=campaign_sha256,
                contract_sha256="c" * 64,
                source_state={"source_sha": source_sha, "clean": True},
                profile=V30_PROFILE,
                allow_missing_numerical_output_for_v31_worker_failure=True,
                expected_campaign_window_path=window_path,
            )

    watchdog["descendants_cleared"] = False
    watchdog_path.write_text(json.dumps(watchdog), encoding="utf-8")
    summary["resource_authority"] = watchdog
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    assert not _v31_missing_numerical_output_is_bound_worker_failure(
        input_path=input_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        numerical_path=numerical_path,
        repo_root=root,
        source_sha=source_sha,
        campaign_sha256=campaign_sha256,
        campaign_window_path=window_path,
    )


@pytest.mark.parametrize("review_version", ["V31", "V32", "V33"])
def test_service_validates_prepared_v31_v32_and_v33_stage_inputs(
    tmp_path, monkeypatch, review_version
):
    import shutil
    import subprocess

    from scripts import task40_v20_service_workflow as service
    from src.runners import task40_v30_contract, task40_v31_contract

    version_suffix = review_version.lower()
    source_root = Path(task40_v31_contract.__file__).resolve().parents[2]
    root = tmp_path / "repo"
    root.mkdir()

    def copy_into_fixture(relative_path):
        source = source_root / relative_path
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    canonical_path = copy_into_fixture(task40_v30_contract.V30_CANONICAL_INPUT_RELATIVE)
    selector_donor_path = (
        root
        / task40_v30_contract.V30_ARTIFACT_ROOT_RELATIVE
        / "q0_selector_v30_partial.json"
    )
    selector_donor_path.parent.mkdir(parents=True, exist_ok=True)
    donor_selector, pinned_manifest, pinned_native = _old_v30_q0_selector_fixture(
        root, source_root
    )
    selector_donor_path.write_text(
        json.dumps(donor_selector, sort_keys=True) + "\n", encoding="utf-8"
    )
    if review_version in {"V32", "V33"}:
        review_path_text = getattr(task40_v31_contract, f"{review_version}_REVIEW_PATH")
        review_sha = getattr(task40_v31_contract, f"{review_version}_REVIEW_SHA256")
        pending_builder = getattr(
            task40_v31_contract, f"prepare_{version_suffix}_pending_package"
        )
    else:
        review_path_text = task40_v31_contract.V31_REVIEW_PATH
        review_sha = task40_v31_contract.V31_REVIEW_SHA256
        pending_builder = task40_v31_contract.prepare_v31_pending_package
    review_path = copy_into_fixture(Path(review_path_text))
    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == review_sha

    source_sha = "b" * 40

    def fake_check_output(command, **_kwargs):
        if command[:3] == ["git", "branch", "--show-current"]:
            return f"{task40_v31_contract.V31_BRANCH}\n"
        if command[:2] == ["git", "rev-parse"]:
            return f"{source_sha}\n"
        if command[:2] == ["git", "status"]:
            return ""
        raise AssertionError(f"unexpected preparation identity command: {command!r}")

    monkeypatch.setattr(task40_v31_contract.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        task40_v31_contract.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
    )
    if review_version in {"V32", "V33"}:
        def q4_complete_template_fixture(*, execution_root):
            execution_root = Path(execution_root)
            return {
                "schema": task40_v31_contract.V32_Q4_COMPLETE_IMPORT_SCHEMA,
                "q_index": 4,
                "twist_index": 0,
                "profile": task40_v31_contract.V31_PROFILE,
                "shape": [2, 2],
                "operator_identity": {
                    "scientific_input_sha256": "1" * 64,
                    "profile_identity_sha256": "2" * 64,
                    "ordered_mode_sha256": "3" * 64,
                    "q_map_sha256": "4" * 64,
                    "original_h_sha256": "5" * 64,
                },
                "matrix_source_identity": {
                    "source_sha": "a" * 40,
                    "window_sha256": "b" * 64,
                },
                "producer_identity": {"kind": "service-route-fixture"},
                "producer_execution_identity": {
                    "source_sha": "c" * 40,
                    "window_sha256": "d" * 64,
                },
                "native_execution_identity": {
                    "source_sha": "c" * 40,
                    "window_sha256": "d" * 64,
                },
                "csr_manifest": {
                    "path": str(
                        execution_root
                        / task40_v31_contract.V32_Q4_COMPLETE_MANIFEST_RELATIVE
                    ),
                    "sha256": "6" * 64,
                },
                "native_qualification": {
                    "path": str(
                        execution_root
                        / task40_v31_contract.V32_Q4_COMPLETE_NATIVE_RELATIVE
                    ),
                    "sha256": "7" * 64,
                    "status": "PASS",
                },
                "csr_artifacts": {
                    name: {
                        "path": str(execution_root / f"q4_{name}.npy"),
                        "bytes": 1,
                        "sha256": f"{index:x}" * 64,
                    }
                    for index, name in enumerate(("data", "indices", "indptr"), start=8)
                },
            }

        monkeypatch.setattr(
            task40_v31_contract,
            "v32_q4_complete_import_template",
            q4_complete_template_fixture,
        )

    consumer_window_sha = "9" * 64
    package = pending_builder(
        repo_root=root,
        execution_root=root,
        consumer_window_sha256=consumer_window_sha,
    )
    contract_path = Path(package["contract"]["path"])
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    selector_path = Path(str(contract["execution"]["selector_path"]))
    if not selector_path.is_absolute():
        selector_path = root / selector_path
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    q0_entry = selector["q_csr_entries"][0]
    fill_identity = pinned_manifest["numeric_fill_identity"]["execution_identity"]
    from src.runners.task40_v30_contract import V30_Q0_DONOR

    assert q0_entry["operator_identity"] == donor_selector["q_csr_entries"][0]["operator_identity"]
    assert q0_entry["matrix_source_identity"] == donor_selector["q_csr_entries"][0]["matrix_source_identity"]
    assert q0_entry["execution_identity"] == {
        "source_sha": source_sha,
        "window_sha256": consumer_window_sha,
    }
    assert q0_entry["native_qualification"] == pinned_manifest["native_qualification"]
    assert q0_entry["legacy_q0_import"]["original_pattern_manifest"] == pinned_native[
        "original_pattern_manifest"
    ]
    assert q0_entry["legacy_q0_import"]["v28_identity"] == {
        "input_sha256": fill_identity["input_sha256"],
        "physical_model_sha256": fill_identity["physical_model_sha256"],
        "run_id": fill_identity["run_id"],
        "campaign_window_sha256": fill_identity["campaign_window_sha256"],
        "mode_manifest_sha256": fill_identity["mode_manifest_sha256"],
        "ordered_mode_key_sha256": fill_identity["ordered_mode_key_sha256"],
        "donor_identity_sha256": pinned_manifest["donor_identity_sha256"],
        "manifest_sha256": V30_Q0_DONOR["manifest_sha256"],
        "native_qualification_sha256": V30_Q0_DONOR["native_qualification_sha256"],
    }
    assert hashlib.sha256(selector_path.read_bytes()).hexdigest() == contract["execution"]["selector_sha256"]
    input_path = Path(str(contract["execution"]["input_path"]))
    if not input_path.is_absolute():
        input_path = root / input_path
    canonical_text = canonical_path.read_text(encoding="utf-8")
    _raw, data = service._read_case(input_path)

    identity_calls = []
    original_identity_check = task40_v31_contract.require_v31_input_identity

    def capture_identity_call(*args, **kwargs):
        identity_calls.append(
            (
                kwargs.get("q4_numeric_pending_import"),
                kwargs.get("q4_complete_import"),
            )
        )
        return original_identity_check(*args, **kwargs)

    monkeypatch.setattr(
        task40_v31_contract,
        "require_v31_input_identity",
        capture_identity_call,
    )
    service._validate_service_stage_input_variant(
        input_path,
        canonical_path,
        canonical_text,
        "full",
        data,
        repo_root=root,
        v31_contract=contract,
    )
    from scripts import run_case

    assert run_case.main([str(input_path), "--validate-only"]) == 0
    if review_version in {"V32", "V33"}:
        expected_template = contract["preparation"]["q4_numeric_pending_import"]
        expected_complete_template = contract["preparation"]["q4_complete_import"]
        expected_identity_call = (expected_template, expected_complete_template)
        assert identity_calls == [expected_identity_call]

        # Exercise the real startup function through both identity checks. Stop
        # at campaign routing, before activation or any child process starts.
        approved_contract = json.loads(json.dumps(contract))
        approved_contract["status"] = "USER_APPROVED"
        approved_contract["service_start_allowed"] = True
        service_window_path = root / f"fixture_campaign_window_{version_suffix}.json"
        service_window_sha = "d" * 64
        approved_contract["execution"]["campaign_window_path"] = str(service_window_path)
        approved_contract["execution"]["campaign_window_sha256"] = service_window_sha
        approved_contract["execution"]["window"].update(
            {
                "window_path": str(service_window_path),
                "window_sha256": service_window_sha,
                "source_at_entry": "c" * 40,
            }
        )
        service_contract_path = (
            root
            / task40_v31_contract.v31_source_artifact_relative(source_sha)
            / f"execution_contract_{version_suffix}.approved.json"
        )
        service_contract_path.parent.mkdir(parents=True, exist_ok=True)
        service_contract_path.write_text("fixture approved contract\n", encoding="utf-8")
        service_contract_sha = "f" * 64

        class ReachedCampaignRouting(Exception):
            pass

        def stop_at_campaign_routing(*_args, **kwargs):
            assert kwargs["v31_contract"]["preparation"]["q4_complete_import"] == (
                expected_complete_template
            )
            raise ReachedCampaignRouting

        with monkeypatch.context() as startup_patch:
            startup_patch.setattr(
                task40_v31_contract,
                "require_v31_execution_contract",
                lambda *_args, **_kwargs: (approved_contract, service_contract_sha),
            )
            startup_patch.setattr(
                service,
                "_resolve_service_campaign",
                stop_at_campaign_routing,
            )
            startup_patch.setenv(
                "TASK40_V31_CONTRACT_PATH", str(service_contract_path)
            )
            startup_patch.setenv(
                "TASK40_V31_CONTRACT_SHA256", service_contract_sha
            )
            with pytest.raises(ReachedCampaignRouting):
                service.run_service(
                    unit=f"task40-{version_suffix}-identity-fixture.service",
                    runtime_prefix=(root / task40_v30_contract.V30_RUNTIME_RELATIVE).resolve(),
                    abi_receipt=(root / task40_v30_contract.V30_ABI_RECEIPT_RELATIVE).resolve(),
                    jit_cache=(root / task40_v30_contract.V30_JIT_CACHE_RELATIVE).resolve(),
                    case_args=[
                        f"--task40-{version_suffix}-execution-contract",
                        str(service_contract_path),
                        str(input_path),
                    ],
                    repo_root=root,
                )
        assert identity_calls[1:] == [expected_identity_call, expected_identity_call]
        from src.io import load_and_resolve

        resolved = load_and_resolve(input_path)
        resolved_payload = resolved.as_jsonable()
        assert resolved_payload["execution"]["task40_v31_q_csr_import_authorizations"] == {
            "complete": {"4": expected_complete_template},
            "numeric_pending": {"4": expected_template}
        }
        from src.runners import task038_full3d_iterative, task40_v20_stage_runner

        route_contract = json.loads(json.dumps(contract))
        route_execution = route_contract["execution"]
        source_at_entry = "c" * 40
        window_path = (
            root
            / task40_v31_contract.V31_ARTIFACT_ROOT_RELATIVE
            / f"source_{source_at_entry}/campaign_window_{version_suffix}.json"
        )
        window_sha = "9" * 64
        route_execution["window"].update(
            {
                "window_path": str(window_path),
                "window_sha256": window_sha,
                "source_at_entry": source_at_entry,
            }
        )
        route_execution["campaign_window_path"] = str(window_path)
        route_execution["campaign_window_sha256"] = window_sha
        route_contract_path = (
            root
            / task40_v31_contract.V31_ARTIFACT_ROOT_RELATIVE
            / f"source_{source_sha}/execution_contract_{version_suffix}.approved.json"
        )
        route_contract_path.parent.mkdir(parents=True, exist_ok=True)
        route_contract_raw = (json.dumps(route_contract, sort_keys=True) + "\n").encode()
        route_contract_path.write_bytes(route_contract_raw)
        route_contract_sha = hashlib.sha256(route_contract_raw).hexdigest()
        route_environment = {
            "TASK40_V31_STRICT_EXECUTION": "1",
            "TASK40_V31_CONTRACT_PATH": str(route_contract_path),
            "TASK40_V31_CONTRACT_SHA256": route_contract_sha,
            "TASK40_V31_EXECUTION_WINDOW_PATH": str(window_path.resolve()),
            "TASK40_V31_EXECUTION_WINDOW_SHA256": window_sha,
            "TASK40_V31_TASK_MEMORY_MAX_BYTES": str(
                route_execution["resources"]["task_memory_max_bytes"]
            ),
            "TASK40_V31_HOST_RESERVE_BYTES": str(
                route_execution["resources"]["host_reserve_bytes"]
            ),
            "TASK40_V31_MEMORY_SWAP_MAX_BYTES": str(
                route_execution["resources"]["memory_swap_max_bytes"]
            ),
        }

        def load_route_contract(path, expected_sha256=None, current_root=None):
            assert Path(path).resolve() == route_contract_path.resolve()
            assert expected_sha256 == route_contract_sha
            assert Path(current_root).resolve() == root.resolve()
            return route_contract, route_contract_sha

        monkeypatch.setattr(
            task40_v31_contract,
            "require_v31_execution_contract",
            load_route_contract,
        )
        route = task40_v31_contract.require_v31_all_q_route(
            resolved_payload,
            source_sha=source_sha,
            repo_root=root,
            environment=route_environment,
        )
        assert route["contract"]["schema"] == task40_v31_contract.V32_CONTRACT_SCHEMA
        assert route["contract_sha256"] == route_contract_sha
        assert route["input_identity"]["staged_input_sha256"] == resolved.input_sha256

        for name, value in route_environment.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(
            task038_full3d_iterative,
            "__file__",
            str(root / "src/runners/task038_full3d_iterative.py"),
        )
        dispatched = {}

        def capture_stage(payload, directory, **kwargs):
            dispatched["payload"] = payload
            dispatched["directory"] = Path(directory)
            dispatched["kwargs"] = kwargs
            return {"status": f"{review_version}_AUTHORITY_ROUTE_VALIDATED_NO_FE"}

        monkeypatch.setattr(
            task40_v20_stage_runner,
            "run_task40_v20_stage",
            capture_stage,
        )
        dispatcher_result = task038_full3d_iterative.run_full3d_iterative(
            resolved_payload,
            root / "dispatcher-output",
            source_sha=source_sha,
        )
        assert dispatcher_result["status"] == f"{review_version}_AUTHORITY_ROUTE_VALIDATED_NO_FE"
        assert dispatched["payload"]["execution"][
            "task40_v31_q_csr_import_authorizations"
        ] == {
            "complete": {"4": expected_complete_template},
            "numeric_pending": {"4": expected_template},
        }
        assert dispatched["payload"]["solver"]["task40_factor_lifecycle_strategy"] == "ALL_Q_RESIDENT"
        assert dispatched["kwargs"]["v31_requested_factor_lifecycle_strategy"] == "ONE_Q_REFACTOR_V19"

        original_text = input_path.read_text(encoding="utf-8")
        tampered_text = original_text.replace(
            "REQUIRE_EXISTING_NUMERIC_PENDING", "ALLOW_REBUILD", 1
        )
        assert tampered_text != original_text
        input_path.write_text(tampered_text, encoding="utf-8")
        assert run_case.main([str(input_path), "--validate-only"]) == 2
        _tampered_raw, tampered_data = service._read_case(input_path)
        with pytest.raises(ValueError, match="outside its registered route"):
            service._validate_service_stage_input_variant(
                input_path,
                canonical_path,
                canonical_text,
                "full",
                tampered_data,
                repo_root=root,
                v31_contract=contract,
            )
    else:
        assert identity_calls == [(None, None)]
        original_text = input_path.read_text(encoding="utf-8")
        injected_text = original_text.replace(
            "task40_v31_factor_bank_config = {",
            'task40_v31_q_csr_import_authorizations = { "numeric_pending" = '
            '{ "4" = { "policy" = "REQUIRE_EXISTING_NUMERIC_PENDING" } } }\n'
            "task40_v31_factor_bank_config = {",
            1,
        )
        assert injected_text != original_text
        input_path.write_text(injected_text, encoding="utf-8")
        assert run_case.main([str(input_path), "--validate-only"]) == 2
        _injected_raw, injected_data = service._read_case(input_path)
        with pytest.raises(ValueError, match="outside its registered route"):
            service._validate_service_stage_input_variant(
                input_path,
                canonical_path,
                canonical_text,
                "full",
                injected_data,
                repo_root=root,
                v31_contract=contract,
            )


def test_v32_pending_commands_keep_same_window_reuse_and_supervisor_under_real_service(tmp_path, monkeypatch):
    import subprocess

    from src.runners import task40_v31_contract

    root = tmp_path / "repo"
    root.mkdir()
    review_path = root / task40_v31_contract.V32_REVIEW_PATH
    review_path.parent.mkdir(parents=True)
    actual_review = Path(task40_v31_contract.__file__).resolve().parents[2] / task40_v31_contract.V32_REVIEW_PATH
    review_path.write_bytes(actual_review.read_bytes())
    assert hashlib.sha256(review_path.read_bytes()).hexdigest() == task40_v31_contract.V32_REVIEW_SHA256

    def fake_check_output(command, **_kwargs):
        if command[:3] == ["git", "branch", "--show-current"]:
            return f"{task40_v31_contract.V31_BRANCH}\n"
        if command[:2] == ["git", "rev-parse"]:
            return "a" * 40 + "\n"
        if command[:2] == ["git", "status"]:
            return " M src/test/fixture.py\n"
        raise AssertionError(f"unexpected package identity command: {command!r}")

    monkeypatch.setattr(task40_v31_contract.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        task40_v31_contract.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0),
    )
    package = task40_v31_contract.prepare_v32_pending_package(
        repo_root=root,
        execution_root=root,
    )
    commands = package["commands"]
    same_window = commands["prepare_same_window_after_source_fix"]
    assert "prepare-v32-approved" in same_window
    assert '--reuse-approved-contract "$V32_EXISTING_APPROVED_CONTRACT"' in same_window
    assert "prepare-v31-approved" not in same_window
    assert "V31_EXISTING_APPROVED_CONTRACT" not in same_window
    service_command = commands["single_supervised_service_after_approved_package"]
    assert "scripts/run_case_in_user_service.sh" in service_command
    assert "--task40-v32-execution-contract" in service_command
    assert "required_checker_and_cleanup" not in commands
    assert "supervision request" in package["service_handoff"]
    assert "check-partial command as supervised completion" in package["service_handoff"]


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
    original_selector, pinned_manifest, pinned_native = _old_v30_q0_selector_fixture(
        root, repository_root
    )
    selector_donor.write_text(
        json.dumps(original_selector, sort_keys=True) + "\n", encoding="utf-8"
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
    assert all(
        attempt["consumer_window_sha256"]
        == hashlib.sha256(window_path.read_bytes()).hexdigest()
        for attempt in pending_attempts
    )
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
    approved_selector_path = Path(approved_contract["execution"]["selector_path"])
    if not approved_selector_path.is_absolute():
        approved_selector_path = root / approved_selector_path
    approved_selector = json.loads(approved_selector_path.read_text(encoding="utf-8"))
    approved_entry = approved_selector["q_csr_entries"][0]
    fill_identity = pinned_manifest["numeric_fill_identity"]["execution_identity"]
    from src.runners.task40_v30_contract import V30_Q0_DONOR

    assert approved_entry["operator_identity"] == original_selector["q_csr_entries"][0]["operator_identity"]
    assert approved_entry["matrix_source_identity"] == original_selector["q_csr_entries"][0]["matrix_source_identity"]
    assert approved_entry["execution_identity"] == {
        "source_sha": source_sha,
        "window_sha256": hashlib.sha256(window_path.read_bytes()).hexdigest(),
    }
    assert approved_entry["native_qualification"] == pinned_manifest["native_qualification"]
    assert approved_entry["legacy_q0_import"]["original_pattern_manifest"] == pinned_native[
        "original_pattern_manifest"
    ]
    assert approved_entry["legacy_q0_import"]["v28_identity"] == {
        "input_sha256": fill_identity["input_sha256"],
        "physical_model_sha256": fill_identity["physical_model_sha256"],
        "run_id": fill_identity["run_id"],
        "campaign_window_sha256": fill_identity["campaign_window_sha256"],
        "mode_manifest_sha256": fill_identity["mode_manifest_sha256"],
        "ordered_mode_key_sha256": fill_identity["ordered_mode_key_sha256"],
        "donor_identity_sha256": pinned_manifest["donor_identity_sha256"],
        "manifest_sha256": V30_Q0_DONOR["manifest_sha256"],
        "native_qualification_sha256": V30_Q0_DONOR["native_qualification_sha256"],
    }
    assert hashlib.sha256(approved_selector_path.read_bytes()).hexdigest() == approved_contract["execution"]["selector_sha256"]
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
