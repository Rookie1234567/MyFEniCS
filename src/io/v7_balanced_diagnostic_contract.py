"""Small stdlib-only launch binding for the optional V7 BAL_H observer."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


V7_PROFILE = "dual_condensed_balh_native_0p7nm_aniso_n0_p4_full_v7"
V7_DIAGNOSTIC_ENV = "TASK39EXTRA_V7_BALANCED_FAILURE_DIAGNOSTIC"
V7_NUMERICAL_BASELINE_SOURCE_SHA = "00789bd1ae41fc7bddbe47d049624eb520de888b"
V7_DIAGNOSTIC_SCHEMA = "task039extra.v7-balanced-failure-launch.v1"


def diagnostic_requested(profile: str, environment_value: str | None) -> bool:
    """Validate the explicit opt-in without importing FE or numerical modules."""

    if environment_value is None:
        return False
    if environment_value != "1":
        raise ValueError(f"{V7_DIAGNOSTIC_ENV} must be unset or exactly '1'")
    if str(profile) != V7_PROFILE:
        raise ValueError("the BAL_H failure observer is restricted to the explicit V7 profile")
    return True


def launch_contract(
    *,
    profile: str,
    execution_mode: str,
    environment_value: str | None,
    source_sha: str,
    input_sha256: str,
    resolved_config_sha256: str,
    physical_model_sha256: str,
    output_directory: str | Path,
) -> dict[str, Any] | None:
    """Return the exact observer contract recorded in the run manifest."""

    if not diagnostic_requested(profile, environment_value):
        return None
    if str(execution_mode) != "full_solve":
        raise ValueError("the V7 diagnostic opt-in requires the full_solve execution mode")
    identities = {
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "resolved_config_sha256": resolved_config_sha256,
        "physical_model_sha256": physical_model_sha256,
    }
    for label, value in identities.items():
        expected_length = 40 if label == "source_sha" else 64
        if len(str(value)) != expected_length:
            raise ValueError(f"{label} must be a complete hexadecimal identity")
        if any(character not in "0123456789abcdef" for character in str(value)):
            raise ValueError(f"{label} must be lowercase hexadecimal")
    return {
        "schema": V7_DIAGNOSTIC_SCHEMA,
        "enabled": True,
        "profile": V7_PROFILE,
        "execution_mode": "full_solve",
        "environment_binding": {"name": V7_DIAGNOSTIC_ENV, "value": "1"},
        "activation_stage": "after_setup_qa_before_outer_fgmres",
        "capture_policy": "first_outer_BAL_H_initial_balance_rejection_only",
        "on_balance_pass": "continue_full_v7_solve",
        "solver_iteration_or_call_limit_added": False,
        "numerical_gate_or_arithmetic_changed": False,
        "observer_report_is_solver_qualification": False,
        "numerical_baseline_source_sha": V7_NUMERICAL_BASELINE_SOURCE_SHA,
        "diagnostic_implementation_source_sha": str(source_sha),
        **identities,
        "output_directory": str(Path(output_directory).resolve()),
    }


def validate_worker_binding(
    manifest: Mapping[str, Any],
    *,
    environment_value: str | None,
    profile: str,
    source_sha: str,
    input_sha256: str,
    resolved_config_sha256: str,
    physical_model_sha256: str,
    output_directory: str | Path,
) -> dict[str, Any] | None:
    """Require worker env, selected V7 profile, and parent manifest to agree."""

    expected = launch_contract(
        profile=profile,
        execution_mode=str(manifest.get("execution_mode", "")),
        environment_value=environment_value,
        source_sha=source_sha,
        input_sha256=input_sha256,
        resolved_config_sha256=resolved_config_sha256,
        physical_model_sha256=physical_model_sha256,
        output_directory=output_directory,
    )
    recorded_present = "v7_balanced_failure_diagnostic" in manifest
    recorded = manifest.get("v7_balanced_failure_diagnostic")
    if expected is None:
        if recorded_present:
            raise ValueError("run manifest enables an observer absent from the worker environment")
        return None
    if not recorded_present or recorded != expected:
        raise ValueError("worker observer request does not match the run manifest identity")
    return expected
