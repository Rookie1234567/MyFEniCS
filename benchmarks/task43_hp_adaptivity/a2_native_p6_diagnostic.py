"""Thin frozen-contract adapter for the two Task43 native-P6 A2 endpoints."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
)
_PLAN_REL = Path("docs/task43_hp_adaptivity/diagnostic_plan_v2.md")
_CONTRACT_SHA256 = "33a5d94ea8c61a26fb1d55c6268709fd283acc549beaeba429833aa68f5055cc"
_A2_NATIVE_CONTRACT_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_a2_native_contract.json"
)
_A2_NATIVE_CONTRACT_SHA256 = (
    "77c533673eba4178868ef22f4a27f8d7ecfbf50d6a47acbcbf2fe45b269960d0"
)
_A2_Q_RETRY_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/"
    "diagnostic_plan_v2_a2_q_retry_authorization.json"
)
_A2_Q_RETRY_SHA256 = "f6b004d30e524a2c3560b6117983762c293602c5ddee8d92f2d9de40ffe073ed"
_PLAN_SHA256 = "864330a9a8d7efeeb1e9e48c73cf48331a9a4963a1bcea1ae061c00c769b455e"
_V3_CONTRACT_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v3_contract.json"
)
_V3_PLAN_REL = Path("docs/task43_hp_adaptivity/diagnostic_plan_v3.md")
# Filled only when the V3 plan/contract and source are frozen for root review.
_V3_CONTRACT_SHA256: str | None = "b694a975dee21d8347d77b3c247edda313422c9f2f6c5c605f8bcb52161e3898"
_V3_PLAN_SHA256: str | None = "b162512ed484ae30b88555b83afe0ad0ac669014e18cf1f1114f24c02bdb1db7"
_Y6_ROOT = Path("benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1")
_Y6_INPUT_SHA256 = "57ad47a4a5ce221bf0e420b4faea084c0557bcd19de29b605e62d50a2bbaeedc"
_Y6_SUMMARY_SHA256 = "1323cb258e65e75ea5ae76bdb4c9d6d6d25c7465f486094dc22b7c7264e4bafc"
_Y6_ROWS_SHA256 = "667871dbebed4319e23190173941e1cfd7d647b9bf1e99d2f9fbec4d4d6ae463"
_Y6_BUNDLE_SHA256 = "6c244fae7e246c171cef1f66ae3f1d607622c89da1f9cd4474e55908bfd6b6d4"
_Y6_IDENTITY_SHA256 = "ef77da1e68136e08b48dc0e352690f9c9fdcd132dcc2b765dcb12413b7cf3300"
_Q8_SAMPLES_SHA256 = "ce3707052419ada5a8e55574a826772bcb1e37cf1f764fc115eb8bf8a52306e5"
_Q10_SAMPLES_SHA256 = "895b65ffbf63176ac20008e6488c1c1318141f877eb5814496fcc945c049514d"
_ROOT_AUDITS = {
    "source_continuity": (
        Path(
            "benchmarks/artifacts/task43/v2_root_audit/a2_native_source_continuity.json"
        ),
        "df200ed48659a7481f641583ecde63d4dd51d8f0d1a573dd38a86d8b0f0c932f",
    ),
    "axis_profile": (
        Path("benchmarks/artifacts/task43/v2_root_audit/a2_axis_profile_replay.json"),
        "c221bb2fe211332c20f3259160d9953de60dce5411ebc66dd4d8de5e96c81acb",
    ),
    "mode_policy": (
        Path("benchmarks/artifacts/task43/v2_root_audit/a2_mode_policy_replay.json"),
        "008d806c25f925684c5d0c600d805cea2df4c714b70a5c08d8a4b0cd8549bf7d",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object at {path}")
    return value


def _preserve_and_demote_v3_comparison(
    comparison_path: Path | None, *, phase: str, error: BaseException
) -> dict[str, Any] | None:
    """Retain exact comparison bytes, then remove their current authority."""

    if comparison_path is None or not comparison_path.is_file():
        return None

    from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
        write_atomic_bytes,
        write_atomic_json,
    )

    comparison_path = Path(comparison_path)
    original_bytes = comparison_path.read_bytes()
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()
    sidecar = comparison_path.with_name(
        f"{comparison_path.name}.pre_failure.{original_sha256}.json"
    )
    if sidecar.exists():
        if sidecar.read_bytes() != original_bytes:
            raise FileExistsError(
                f"pre-failure comparison sidecar differs from its source: {sidecar}"
            )
        original_ref = {
            "path": str(sidecar),
            "sha256": original_sha256,
            "bytes": len(original_bytes),
        }
    else:
        original_ref = write_atomic_bytes(sidecar, original_bytes)

    try:
        original = json.loads(original_bytes.decode("utf-8"))
        if not isinstance(original, dict):
            raise TypeError("comparison record must be a JSON object")
        demoted = dict(original)
        previous_qualification = original.get("endpoint_qualified")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as parse_error:
        demoted = {
            "schema": "task43.v3.comparison_authority_failure.v1",
            "original_record_parse_error": str(parse_error),
        }
        previous_qualification = None

    demoted.update(
        {
            "original_record_path": original_ref["path"],
            "current_record_path_before_demotion": str(comparison_path),
            "original_record_sha256": original_sha256,
            "original_endpoint_qualified": previous_qualification,
            "postprocess_failure": {
                "phase": phase,
                "exception_type": type(error).__name__,
                "exception_message": str(error),
            },
            "status": "FAILED_OR_INCOMPLETE_V3_POSTPROCESS",
            "classification": "measured_or_partial_nonofficial_endpoint",
            "authority": "DIAGNOSTIC_ONLY_PARTIAL_NONOFFICIAL",
            "endpoint_qualified": False,
            "official_result": False,
            "passed": False,
            "selection_eligible": False,
            "selection_candidate": False,
            "candidate_selected": False,
            "same_group_R_factor_may_continue": False,
            "A2_R_status": "locked_after_v3_postprocess_failure",
            "continuation_all_false": True,
            "continuation": {
                "same_group_R": False,
                "A1_R": False,
                "A2_q": False,
                "A2_R": False,
                "A2_q3": False,
                "B": False,
                "C": False,
                "cost_campaign": False,
                "iteration": False,
            },
        }
    )
    write_atomic_json(comparison_path, demoted, refuse_overwrite=False)
    return {
        **original_ref,
        "current_path": str(comparison_path),
        "current_sha256": _sha256(comparison_path),
        "authority_demoted": True,
    }


def _task43_v3_postprocess_fail_closed(
    comparison_callback,
    *,
    summary_path: Path,
    run_directory: Path,
    phase: str,
    comparison_path: Path | None = None,
    summary_snapshot: dict[str, Any] | None = None,
) -> Any:
    """Demote cached native and comparison records without masking failures."""

    # Read and deep-copy before any adapter writer can truncate either record.
    cached_summary = copy.deepcopy(
        summary_snapshot if summary_snapshot is not None else _read_json(summary_path)
    )

    try:
        return comparison_callback()
    # Demote authority even for process-level interruptions, then preserve the
    # original exception for the caller.
    except BaseException as exc:
        summary = cached_summary
        identity = summary.get("task43_v3_diagnostic_identity", {})
        from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
            demote_v3_native_summary_after_error,
            write_atomic_json,
        )

        comparison_reference = None
        demotion_errors = []
        try:
            comparison_reference = _preserve_and_demote_v3_comparison(
                comparison_path, phase=phase, error=exc
            )
        # Cleanup failures are recorded without replacing the callback error.
        except BaseException as demotion_error:  # noqa: BLE001
            demotion_errors.append(
                f"comparison authority demotion: {type(demotion_error).__name__}: "
                f"{demotion_error}"
            )

        reported_comparison = summary.get("task43_v2_comparison")
        if isinstance(reported_comparison, dict):
            reported_comparison["endpoint_qualified_before_failure"] = reported_comparison.get(
                "endpoint_qualified"
            )
            reported_comparison.update(
                endpoint_qualified=False,
                same_group_R_factor_may_continue=False,
                A2_R_status="locked_after_v3_postprocess_failure",
                endpoint_qualification_scope=(
                    "non-authoritative after V3 adapter postprocess failure"
                ),
                authority="DIAGNOSTIC_ONLY_PARTIAL_NONOFFICIAL",
            )
            if comparison_reference is not None:
                reported_comparison.update(
                    path=comparison_reference["current_path"],
                    sha256=comparison_reference["current_sha256"],
                    original_record_path=comparison_reference["path"],
                    original_record_sha256=comparison_reference["sha256"],
                )
            summary["task43_v2_comparison"] = reported_comparison
        summary["task43_v3_postprocess_failure"] = {
            "phase": phase,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "comparison_failure_reference": comparison_reference,
            "demotion_errors": demotion_errors,
        }

        try:
            demote_v3_native_summary_after_error(
                summary,
                run_directory / "numerical_output/task43_v3_partial_terminal.json",
                phase=phase,
                source_identity={
                    "source_sha": summary.get("source_sha"),
                    "frozen_v3_contract_sha256": identity.get("contract_sha256"),
                    "frozen_v3_plan_sha256": identity.get("plan_sha256"),
                },
                error=exc,
                primary_before_extra_packet=summary.get(
                    "task43_v3_primary_before_extra_packet"
                ),
                primary_q_samples=summary.get("task43_v3_primary_field_samples", {}),
                extra_q_samples=summary.get("task43_v3_extra_field_samples", {}),
                extra_before_output_packet=summary.get(
                    "task43_v3_extra_before_output_packet"
                ),
                comparison_failure_reference=comparison_reference,
            )
        # Keep the original callback exception if terminal persistence fails.
        except BaseException as demotion_error:  # noqa: BLE001
            demotion_errors.append(
                f"partial terminal write: {type(demotion_error).__name__}: "
                f"{demotion_error}"
            )
            summary["task43_v3_postprocess_failure"]["demotion_errors"] = demotion_errors

        try:
            write_atomic_json(summary_path, summary, refuse_overwrite=False)
        # Keep the original callback exception if summary persistence fails.
        except BaseException as demotion_error:  # noqa: BLE001
            print(
                "Task43 V3 could not persist its fail-closed summary; "
                f"original {type(exc).__name__} remains active: {demotion_error}",
                file=sys.stderr,
                flush=True,
            )
        if demotion_errors:
            print(
                "Task43 V3 failure-record warnings: " + "; ".join(demotion_errors),
                file=sys.stderr,
                flush=True,
            )
        raise


def _validate_v3_a2_entry_contract(
    contract: dict[str, Any], *, phase: str, attempt: int
) -> None:
    """Check the bounded V3 A2_q allocation without changing prior contracts."""

    if phase != "A2_q" or attempt != 3:
        raise ValueError("Task43 V3 only freezes the A2_q attempt-3 route")
    attempts = contract.get("formal_model_attempts", {})
    phases = contract.get("phases", {})
    a2_rows = phases.get("A2", [])
    row = next(
        (
            item
            for item in a2_rows
            if isinstance(item, dict) and item.get("id") == phase
        ),
        None,
    )
    immutable = contract.get("immutable_prior_contracts_and_review", {})
    authority = contract.get("authority", {})
    prohibited = contract.get("prohibited", [])
    terminal_hashes = row.get("old_attempt_terminal_hashes", []) if row else []
    if (
        contract.get("schema") != "task43.v3.finite_diagnostic_contract.v1"
        or contract.get("status") != "frozen_for_execution"
        or immutable.get(
            "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_contract.json"
        )
        != _CONTRACT_SHA256
        or immutable.get(
            "docs/task43_hp_adaptivity/outcomes/records/diagnostic_plan_v2_a2_native_contract.json"
        )
        != _A2_NATIVE_CONTRACT_SHA256
        or attempts.get("total_original_max") != 6
        or attempts.get("already_consumed") != 3
        or attempts.get("new_dispatches_max") != 2
        or attempts.get("cumulative_max_after_this_review") != 5
        or attempts.get("sealed_remaining_unallocated") != 1
        or attempts.get("no_automatic_retry") is not True
        or attempts.get("A1_cumulative_max_this_review") != 2
        or row is None
        or row.get("attempt") != attempt
        or row.get("new_dispatches_max") != 1
        or row.get("operator_q") != 19
        or row.get("incident_port_q") != 32
        or row.get("modal_rectangle") != "R13"
    ):
        raise ValueError("Task43 V3 A2_q entry differs from its frozen allocation")
    if (
        authority.get("review_commit") != "fd7ebd2a60eb6fd7d776f1ca68d367581e8f7d12"
        or authority.get("review_path")
        != "docs/task43_hp_adaptivity/review_report_v2.md"
        or authority.get("execution_section") != "10"
        or attempts.get("A2_cumulative_max_this_review") != 3
        or row.get("normal_corrections_max") != 2
        or row.get("extra_corrections_max") != 1
        or len(terminal_hashes) != 2
        or phases.get("A1_R", {}).get("authorized") is not False
        or phases.get("A2_R", {}).get("authorized") is not False
        or phases.get("B", {}).get("authorized") is not False
        or phases.get("C", {}).get("authorized") is not False
        or not {"A1_R", "A2_R", "B", "C"}.issubset(set(prohibited))
    ):
        raise ValueError("Task43 V3 A2_q contract leaves an unauthorized continuation")
    review_path = _REPO_ROOT / str(authority["review_path"])
    expected_review_sha = immutable.get(str(authority["review_path"]))
    if (
        not isinstance(expected_review_sha, str)
        or _sha256(review_path) != expected_review_sha
    ):
        raise ValueError("Task43 V3 review bytes differ from the frozen review hash")
    ancestry = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            str(authority["review_commit"]),
            "HEAD",
        ],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise ValueError(
            "Task43 V3 review commit is not an ancestor of the execution HEAD"
        )
    terminal_root = _REPO_ROOT / "benchmarks/artifacts/task43/v2_diagnostics"
    for index, expected_hash in enumerate(terminal_hashes, start=1):
        attempt_root = terminal_root / f"A2_q_attempt{index}"
        summary_path = attempt_root / "watchdog/summary.json"
        launcher_code_path = attempt_root / "launcher_exit_code.txt"
        if (
            not summary_path.is_file()
            or _sha256(summary_path) != expected_hash
            or not launcher_code_path.is_file()
            or launcher_code_path.read_text(encoding="utf-8").strip() != "2"
        ):
            raise ValueError(
                f"Task43 V3 A2_q attempt {index} terminal/launcher bytes changed"
            )
        terminal = _read_json(summary_path)
        if (
            terminal.get("classification") != "WORKER_FAILED"
            or terminal.get("leader_exit_code") != 1
            or terminal.get("descendants_cleared") is not True
        ):
            raise ValueError(
                f"Task43 V3 A2_q attempt {index} is not the frozen failed/clean terminal"
            )


def _require_v3_watchdog_worker_identity() -> dict[str, Any]:
    """Verify the post-exec adapter process is the watchdog's direct child."""

    try:
        expected_parent = int(os.environ["PHYSICAL_WATCHDOG_PARENT_PID"])
        phase_path = Path(os.environ["PHYSICAL_WATCHDOG_PHASE_PATH"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("V3 A2 requires native watchdog parent and phase identity") from exc
    actual_parent = os.getppid()
    if expected_parent != actual_parent:
        raise RuntimeError(
            "V3 A2 worker is not the direct child registered by its native watchdog"
        )
    if not phase_path.is_absolute():
        raise RuntimeError("V3 A2 watchdog phase path must be absolute")
    phase_path = phase_path.resolve()
    return {
        "worker_pid": os.getpid(),
        "worker_parent_pid": actual_parent,
        "watchdog_parent_pid_environment": expected_parent,
        "direct_watchdog_parent_verified": True,
        "phase_path": str(phase_path),
    }


def _raw_relative(
    norm: float, scale: float, *, absolute_tolerance: float = 1.0e-12
) -> float:
    """Reproduce the native A6 zero-scale rule used by ``_operation_relative``."""

    if not np.isfinite([norm, scale]).all() or norm < 0.0 or scale < 0.0:
        return float("inf")
    if scale > np.finfo(float).tiny:
        return float(norm / scale)
    return 0.0 if norm <= absolute_tolerance else float("inf")


def _matches_recorded_value(observed: Any, recorded: Any, *, label: str) -> float:
    observed_value = float(observed)
    recorded_value = float(recorded)
    if not np.isfinite([observed_value, recorded_value]).all() or not np.isclose(
        observed_value, recorded_value, rtol=2.0e-11, atol=2.0e-14
    ):
        raise ValueError(f"A2_q raw {label} does not match its recorded scalar")
    return observed_value


def _numpy_array_identity(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _read_a2_residual_vectors(
    path: Path, summary: dict[str, Any]
) -> dict[str, np.ndarray]:
    """Read full residual/RHS vectors, condensed solutions, and normal history."""

    normal_audit = summary.get("task43_v2_normal_correction_audit", {})
    normal_history = normal_audit.get("history", [])
    correction_count = int(normal_audit.get("correction_count", -1))
    if (
        not isinstance(normal_history, list)
        or len(normal_history) != correction_count + 1
    ):
        raise ValueError("A2 endpoint lacks a complete normal-correction history")
    normal_residual_names = tuple(
        f"normal_correction_residual_{index}" for index in range(len(normal_history))
    )
    required_arrays = (
        "primary_condensed_b_minus_Ax",
        "primary_condensed_rhs",
        "primary_condensed_solution",
        "primary_independent_A6_residual",
        "primary_native_A6_effective_rhs",
        "primary_zero_slave_carrier_residual",
        "primary_augmented_port_residual",
        "extra_lu_condensed_b_minus_Ax",
        "extra_lu_condensed_rhs",
        "extra_lu_condensed_solution",
        "extra_lu_independent_A6_residual",
        "extra_lu_native_A6_effective_rhs",
        "extra_lu_zero_slave_carrier_residual",
        "extra_lu_augmented_port_residual",
    ) + normal_residual_names
    matrix_facts = summary.get("matrix", {})
    matrix_shape = tuple(int(value) for value in matrix_facts.get("shape", ()))
    carrier_storage_rows = int(matrix_facts.get("full_p6_storage_rows", 0))
    active_rows = int(matrix_facts.get("active_trace_rows", 0))
    port_rows = int(matrix_facts.get("appended_port_rows", 0))
    expected_modes = int(
        summary.get("operator_identity", {}).get("active_mode_count", 0)
    )
    condensed_rows = active_rows + port_rows
    if (
        len(matrix_shape) != 2
        or matrix_shape[0] <= 0
        or matrix_shape[0] != matrix_shape[1]
        or matrix_shape[0] != condensed_rows
        or carrier_storage_rows <= 0
        or active_rows <= 0
        or expected_modes not in {612, 836}
        or port_rows != expected_modes
    ):
        raise ValueError("A2_q summary has invalid live matrix/full-storage dimensions")
    expected_lengths = {
        name: condensed_rows
        for name in (
            "primary_condensed_b_minus_Ax",
            "primary_condensed_rhs",
            "primary_condensed_solution",
            "extra_lu_condensed_b_minus_Ax",
            "extra_lu_condensed_rhs",
            "extra_lu_condensed_solution",
        )
    }
    expected_lengths.update({name: condensed_rows for name in normal_residual_names})
    expected_lengths.update(
        {
            name: carrier_storage_rows
            for name in (
                "primary_independent_A6_residual",
                "primary_native_A6_effective_rhs",
                "primary_zero_slave_carrier_residual",
                "extra_lu_independent_A6_residual",
                "extra_lu_native_A6_effective_rhs",
                "extra_lu_zero_slave_carrier_residual",
            )
        }
    )
    expected_lengths.update(
        {
            "primary_augmented_port_residual": port_rows,
            "extra_lu_augmented_port_residual": port_rows,
        }
    )
    result: dict[str, np.ndarray] = {}
    with np.load(path, allow_pickle=False) as raw:
        if not set(required_arrays).issubset(raw.files):
            raise ValueError("A2_q residual bundle lacks raw RHS/residual arrays")
        for name in required_arrays:
            values = np.asarray(raw[name])
            if values.ndim != 1 or values.shape != (expected_lengths[name],):
                raise ValueError(
                    f"A2_q raw residual/RHS vector {name} has an unexpected shape"
                )
            result[name] = np.asarray(values, dtype=np.complex128).copy()
    if any(not np.isfinite(value).all() for value in result.values()):
        raise ValueError("A2_q raw residual/RHS array is non-finite")
    if any(value.size == 0 for value in result.values()):
        raise ValueError("A2_q raw residual/RHS array is empty")
    return result


def _recompute_a2_normal_correction_gate(
    summary: dict[str, Any], residual_arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    """Recompute native normal-correction ratios from saved condensed residuals."""

    recorded = summary.get("task43_v2_normal_correction_audit", {})
    history = recorded.get("history", [])
    correction_count = int(recorded.get("correction_count", -1))
    correction_limit = int(recorded.get("correction_limit", -1))
    rhs = residual_arrays["primary_condensed_rhs"]
    rhs_norm = float(np.linalg.norm(rhs))
    denominator = max(rhs_norm, np.finfo(float).tiny)
    structure_matches = bool(
        isinstance(history, list)
        and len(history) == correction_count + 1
        and [int(row.get("correction", -1)) for row in history]
        == list(range(correction_count + 1))
    )
    ratios = []
    norms = []
    for index, row in enumerate(history):
        vector = residual_arrays[f"normal_correction_residual_{index}"]
        norm = float(np.linalg.norm(vector))
        ratio = norm / denominator
        ratios.append(ratio)
        norms.append(norm)
        _matches_recorded_value(
            ratio,
            row.get("relative_residual"),
            label=f"normal correction {index} raw ratio",
        )
        _matches_recorded_value(
            norm,
            row.get("residual_norm_derived_from_recorded_ratio_and_denominator"),
            label=f"normal correction {index} derived norm",
        )
        if index > 0:
            structure_matches = bool(
                structure_matches
                and int(row.get("solve_calls", -1)) == 1 + index
                and int(row.get("symbolic_calls", -1)) == 1
                and int(row.get("numeric_calls", -1)) == 1
                and row.get("solver_method")
                == "native_PETSc_MatSolve_with_MUMPS_factor"
                and row.get("petsc_matsolve_completed_without_exception") is True
                and row.get("solution_updated") is True
                and row.get("ksp_converged_reason") == "not_applicable_native_MatSolve"
            )
    if history:
        structure_matches = bool(
            structure_matches
            and history[0].get("solution_updated") is False
            and history[0].get("solver_method") == "initial_native_direct_solve"
        )
    factor = summary.get("factor", {})
    normal_factor_calls_match = bool(
        int(factor.get("solve_calls", -1)) == 1 + correction_count
        and int(factor.get("symbolic_calls", -1)) == 1
        and int(factor.get("numeric_calls", -1)) == 1
    )
    mumps_info = recorded.get("mumps_info_after_last_solve")
    infog = mumps_info.get("infog") if isinstance(mumps_info, dict) else None
    mumps_info_bound = bool(
        isinstance(infog, dict)
        and isinstance(infog.get("1"), int)
        and not isinstance(infog.get("1"), bool)
        and infog.get("1") == 0
        and recorded.get("mumps_info_after_last_solve")
        == factor.get("mumps_info_after_last_solve")
    )
    finite_nonnegative = bool(
        np.isfinite([rhs_norm, denominator, *ratios, *norms]).all()
        and rhs_norm >= 0.0
        and all(value >= 0.0 for value in ratios)
        and all(value >= 0.0 for value in norms)
    )
    strict_decrease = all(after < before for before, after in pairwise(ratios))
    passed = bool(
        structure_matches
        and normal_factor_calls_match
        and mumps_info_bound
        and finite_nonnegative
        and strict_decrease
        and 0 <= correction_count <= correction_limit
    )
    if recorded.get("passed") is not passed:
        raise ValueError(
            "A2 normal correction PASS field differs from raw-vector audit"
        )
    return {
        "passed": passed,
        "gates": {
            "history_structure_matches_raw_steps": structure_matches,
            "factor_calls_match_raw_steps": normal_factor_calls_match,
            "mumps_infog1_zero_and_bound_to_pre_extra_solve": mumps_info_bound,
            "all_raw_ratios_and_norms_finite_nonnegative": finite_nonnegative,
            "every_executed_correction_strictly_decreased": strict_decrease,
            "within_frozen_correction_limit": 0 <= correction_count <= correction_limit,
        },
        "correction_count": correction_count,
        "rhs_norm": rhs_norm,
        "effective_denominator_norm": denominator,
        "residual_norms_from_raw_vectors": norms,
        "relative_residuals_from_raw_vectors": ratios,
        "solver_method": "native_PETSc_MatSolve_with_MUMPS_factor",
        "ksp_converged_reason": "not_applicable_native_MatSolve",
    }


def _recompute_a2_extra_lu_helper_integrity(
    summary: dict[str, Any], residual_arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    """Recheck one-correction counts, finite vectors, and unchanged primary/RHS."""

    from src.runners.p6_condensed_direct import _task43_v2_array_identity

    linear = summary.get("task43_v2_extra_lu_diagnostic", {}).get(
        "linear_correction", {}
    )
    factor = summary.get("factor", {})
    primary_solution = residual_arrays["primary_condensed_solution"]
    extra_solution = residual_arrays["extra_lu_condensed_solution"]
    condensed_rhs = residual_arrays["primary_condensed_rhs"]
    correction = extra_solution - primary_solution
    primary_identity = _task43_v2_array_identity(primary_solution)
    rhs_identity = _task43_v2_array_identity(condensed_rhs)
    primary_preserved = bool(
        linear.get("primary_solution_preserved") is True
        and linear.get("primary_solution_before_identity") == primary_identity
        and linear.get("primary_solution_after_identity") == primary_identity
    )
    rhs_preserved = bool(
        linear.get("rhs_preserved") is True
        and linear.get("rhs_before_identity") == rhs_identity
        and linear.get("rhs_after_identity") == rhs_identity
    )
    initial_solve_calls = int(linear.get("initial_factor_solve_calls", -1))
    final_solve_calls = int(linear.get("final_factor_solve_calls", -1))
    initial_symbolic_calls = int(linear.get("initial_factor_symbolic_calls", -1))
    final_symbolic_calls = int(linear.get("final_factor_symbolic_calls", -1))
    initial_numeric_calls = int(linear.get("initial_factor_numeric_calls", -1))
    final_numeric_calls = int(linear.get("final_factor_numeric_calls", -1))
    factor_counts_match = bool(
        final_solve_calls - initial_solve_calls == 1
        and linear.get("extra_correction_count") == 1
        and linear.get("exactly_one_extra_solve") is True
        and factor.get("solve_calls_after_extra_lu") == final_solve_calls
        and initial_symbolic_calls == final_symbolic_calls == 1
        and initial_numeric_calls == final_numeric_calls == 1
        and factor.get("symbolic_calls_after_extra_lu") == final_symbolic_calls
        and factor.get("numeric_calls_after_extra_lu") == final_numeric_calls
        and linear.get("factorization_calls_unchanged") is True
    )
    finite = bool(
        linear.get("finite") is True
        and np.isfinite(primary_solution).all()
        and np.isfinite(extra_solution).all()
        and np.isfinite(correction).all()
        and np.isfinite(condensed_rhs).all()
        and np.isfinite(float(linear.get("correction_norm", float("nan"))))
    )
    correction_norm = float(np.linalg.norm(correction))
    _matches_recorded_value(
        correction_norm,
        linear.get("correction_norm"),
        label="raw condensed correction norm",
    )
    original_helper_gates = {
        "original_helper_status_passed": linear.get("original_helper_status") == "PASS",
        "exactly_one_extra_solve": factor_counts_match,
        "factorization_calls_unchanged": linear.get("factorization_calls_unchanged")
        is True,
        "finite": finite,
        "primary_solution_preserved": primary_preserved,
        "rhs_preserved": rhs_preserved,
        "matrix_object_identity_same": linear.get("matrix_object_identity_same")
        is True,
    }
    recorded_gates_match = linear.get("original_helper_gates") == original_helper_gates
    passed = bool(all(original_helper_gates.values()) and recorded_gates_match)
    return {
        "passed": passed,
        "gates": original_helper_gates,
        "recorded_original_helper_gates_match_raw": recorded_gates_match,
        "primary_solution_identity_from_raw": primary_identity,
        "condensed_rhs_identity_from_raw": rhs_identity,
        "correction_norm_from_raw": correction_norm,
        "factor_call_counts": {
            "initial_solve_calls": initial_solve_calls,
            "final_solve_calls": final_solve_calls,
            "initial_symbolic_calls": initial_symbolic_calls,
            "final_symbolic_calls": final_symbolic_calls,
            "initial_numeric_calls": initial_numeric_calls,
            "final_numeric_calls": final_numeric_calls,
        },
    }


def _a2_attempt_run_directory(
    attempt_root: Path, requested: Path | None = None
) -> Path:
    """Require a fresh runner child under the precreated launch/watchdog root."""

    attempt_root = attempt_root.resolve()
    required_dir = (attempt_root / "run").resolve()
    output_dir = required_dir if requested is None else requested.resolve()
    if output_dir != required_dir:
        raise ValueError(
            "Task43 A2 runner output must be the frozen attempt-root/run child"
        )
    if not attempt_root.is_dir():
        raise FileNotFoundError(
            "Task43 A2 requires the precreated watchdog/launch attempt root"
        )
    if output_dir.exists():
        raise FileExistsError(f"Task43 A2 attempt path already exists: {output_dir}")
    return output_dir


def _require_a2_q_r13_same_source_identity(
    summary: dict[str, Any], current_source_sha: str
) -> None:
    """Require A2_R to reuse the exact committed q19/q32/R13 A2_q source."""

    diagnostic_identity = summary.get("task43_v2_diagnostic_identity", {})
    bindings = summary.get("task43_v2_input_bindings", {})
    operator = summary.get("operator_identity", {})
    actual_route = summary.get("task43_v2_actual_quadrature_route", {})
    volume_route = actual_route.get("volume_action_and_condensation", {})
    rhs_route = actual_route.get("incident_and_port_rhs", {})
    expected_volume_metadata = [
        {"quadrature_degree": 19, "quadrature_rule": "default"},
        {"quadrature_degree": 19, "quadrature_rule": "default"},
    ]
    actual_components = volume_route.get("actual_component_integral_metadata", {})
    combined_metadata = volume_route.get("actual_combined_form_integral_metadata", [])
    component_q19 = bool(
        set(actual_components) == {"curl", "material_mass"}
        and all(rows for rows in actual_components.values())
        and bool(combined_metadata)
        and all(
            item.get("quadrature_degree") == 19
            and item.get("quadrature_rule") == "default"
            for rows in actual_components.values()
            for item in rows
        )
        and all(
            item.get("quadrature_degree") == 19
            and item.get("quadrature_rule") == "default"
            for item in combined_metadata
        )
    )
    if (
        summary.get("source_sha") != current_source_sha
        or diagnostic_identity.get("phase") != "A2_q"
        or diagnostic_identity.get("volume_quadrature_degree") != 19
        or diagnostic_identity.get("incident_quadrature_degree") != 32
        or diagnostic_identity.get("port_quadrature_degree") != 32
        or diagnostic_identity.get("modal_rectangle_max_abs_m_n") != [4, 8]
        or diagnostic_identity.get("mode_basis_scale_policy") is not None
        or diagnostic_identity.get("normal_correction_max") != 2
        or diagnostic_identity.get("extra_correction_max") != 1
        or diagnostic_identity.get("a2_native_contract_sha256")
        != _A2_NATIVE_CONTRACT_SHA256
        or diagnostic_identity.get("frozen_plan_sha256") != _CONTRACT_SHA256
        or diagnostic_identity.get("frozen_plan_markdown_sha256") != _PLAN_SHA256
        or bindings.get("contract_sha256") != _CONTRACT_SHA256
        or bindings.get("a2_native_contract_sha256") != _A2_NATIVE_CONTRACT_SHA256
        or bindings.get("a2_native_contract_path")
        != str((_REPO_ROOT / _A2_NATIVE_CONTRACT_REL).resolve())
        or bindings.get("plan_markdown_sha256") != _PLAN_SHA256
        or operator.get("operator_scope")
        != "task43_v2_A2_R13_native_Y6_1_finite_rectangle"
        or operator.get("parent_quadrature_degree") != 32
        or operator.get("active_mode_count") != 612
        or operator.get("parent_mode_count") != 612
        or operator.get("volume_quadrature_metadata_used_by_condensation_form")
        != expected_volume_metadata
        or operator.get(
            "volume_quadrature_metadata_used_by_independent_physical_action"
        )
        != expected_volume_metadata
        or rhs_route.get("cfg_incident_degree") != 32
        or rhs_route.get("bundle_dtn_degree") != 32
        or volume_route.get("quadrature_degree") != 19
        or volume_route.get("same_bundle_form_drives_physical_action_and_condensation")
        is not True
        or not component_q19
    ):
        raise ValueError(
            "A2_R requires the same committed q19/q32/R13 native unscaled A2_q endpoint"
        )


def _raw_modal_volume_output(
    *,
    label: str,
    modal_path: Path,
    modal_sha256: str,
    volume_path: Path,
    volume_sha256: str,
    output_facts: dict[str, Any],
    physical_sha256: str,
    discretization_sha256: str,
) -> dict[str, Any]:
    """Validate complete raw R13 rows and independently recompute R/T/A closure."""

    from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
        R13_MODE_KEYS,
        compare_r13_modal_outputs,
    )

    if _sha256(modal_path) != modal_sha256 or _sha256(volume_path) != volume_sha256:
        raise ValueError(f"A2_q {label} raw modal/volume output hash changed")
    payload = _read_json(modal_path)
    volume = _read_json(volume_path)
    a_volume = float(volume["A_volume_total"])
    raw_rows = compare_r13_modal_outputs(
        payload,
        payload,
        reference_a_volume=a_volume,
        candidate_a_volume=a_volume,
        reference_physical_configuration_sha256=physical_sha256,
        candidate_physical_configuration_sha256=physical_sha256,
        reference_discretization_sha256=discretization_sha256,
        candidate_discretization_sha256=discretization_sha256,
        expected_keys=R13_MODE_KEYS,
    )
    aggregate = raw_rows["aggregate_power"]["candidate"]
    raw_closure = float(aggregate["R_total"] + aggregate["T_total"] + a_volume - 1.0)
    volume_closure = _matches_recorded_value(
        volume["energy_closure_error_port_volume"],
        raw_closure,
        label=f"{label} volume closure",
    )
    if not np.isclose(volume_closure, raw_closure, rtol=0.0, atol=2.0e-14):
        raise ValueError(f"A2_q {label} volume file closure differs from raw rows")

    port_metrics = output_facts.get("port_metrics", {})
    volume_metrics = output_facts.get("volume_metrics", {})
    for metric in ("R_total", "T_total"):
        _matches_recorded_value(
            aggregate[metric], port_metrics.get(metric), label=f"{label} {metric}"
        )
    _matches_recorded_value(
        a_volume, volume_metrics.get("A_volume_total"), label=f"{label} A_volume"
    )
    _matches_recorded_value(
        raw_closure,
        output_facts.get("energy_closure_error_port_volume"),
        label=f"{label} output closure",
    )
    return {
        "modal_rows_path": str(modal_path),
        "modal_rows_sha256": modal_sha256,
        "volume_absorption_path": str(volume_path),
        "volume_absorption_sha256": volume_sha256,
        "mode_count": raw_rows["candidate_inventory"]["mode_count"],
        "R_total_from_rows": float(aggregate["R_total"]),
        "T_total_from_rows": float(aggregate["T_total"]),
        "A_volume_from_file": a_volume,
        "closure_recomputed_from_rows_and_volume": raw_closure,
        "raw_rows_and_aggregate_validation": True,
        "output_finite": bool(
            output_facts.get("electric_finite") is True
            and output_facts.get("auxiliary_finite") is True
        ),
    }


def _recompute_a2_q_raw_hard_gates(
    summary_path: Path, summary: dict[str, Any]
) -> dict[str, Any]:
    """Recompute A2_q hard gates from saved residual/RHS arrays and output files."""

    identity = summary.get("task43_v2_endpoint_identity", {})
    if identity.get("phase") != "A2_q":
        raise ValueError("A2_R raw-gate preflight requires an A2_q endpoint")
    physical_sha = str(identity.get("physical_configuration_sha256", ""))
    discretization_sha = str(identity.get("discretization_sha256", ""))
    if len(physical_sha) != 64 or len(discretization_sha) != 64:
        raise ValueError("A2_q raw-gate preflight lacks endpoint identities")

    primary = summary["task43_v2_primary_endpoint_output"]
    extra = summary["task43_v2_extra_lu_diagnostic"]
    extra_files = extra["field_samples"]
    residual_path = Path(str(primary["same_lu_residual_vectors_path"]))
    residual_sha = str(primary["same_lu_residual_vectors_sha256"])
    if (
        residual_sha != extra_files.get("residual_vectors_sha256")
        or str(residual_path) != str(extra_files.get("residual_vectors_path"))
        or _sha256(residual_path) != residual_sha
    ):
        raise ValueError("A2_q same-LU raw residual bundle identity is inconsistent")
    residual_arrays = _read_a2_residual_vectors(residual_path, summary)
    normal_correction_raw = _recompute_a2_normal_correction_gate(
        summary, residual_arrays
    )
    extra_helper_integrity = _recompute_a2_extra_lu_helper_integrity(
        summary, residual_arrays
    )

    primary_condensed_rhs = residual_arrays["primary_condensed_rhs"]
    extra_condensed_rhs = residual_arrays["extra_lu_condensed_rhs"]
    if not np.array_equal(primary_condensed_rhs, extra_condensed_rhs):
        raise ValueError("A2_q before/after condensed RHS vectors differ")
    primary_a6_rhs = residual_arrays["primary_native_A6_effective_rhs"]
    extra_a6_rhs = residual_arrays["extra_lu_native_A6_effective_rhs"]
    if not np.array_equal(primary_a6_rhs, extra_a6_rhs):
        raise ValueError("A2_q before/after native A6 effective RHS vectors differ")

    primary_condensed_norm = float(
        np.linalg.norm(residual_arrays["primary_condensed_b_minus_Ax"].ravel())
    )
    condensed_rhs_norm = float(np.linalg.norm(primary_condensed_rhs.ravel()))
    primary_condensed_relative = primary_condensed_norm / max(
        condensed_rhs_norm, np.finfo(float).tiny
    )
    extra_condensed_norm = float(
        np.linalg.norm(residual_arrays["extra_lu_condensed_b_minus_Ax"].ravel())
    )
    extra_condensed_relative = extra_condensed_norm / max(
        condensed_rhs_norm, np.finfo(float).tiny
    )
    primary_a6_norm = float(
        np.linalg.norm(residual_arrays["primary_independent_A6_residual"].ravel())
    )
    native_effective_rhs_norm = float(np.linalg.norm(primary_a6_rhs.ravel()))
    primary_a6_relative = _raw_relative(primary_a6_norm, native_effective_rhs_norm)
    extra_a6_norm = float(
        np.linalg.norm(residual_arrays["extra_lu_independent_A6_residual"].ravel())
    )
    extra_a6_rhs_norm = float(np.linalg.norm(extra_a6_rhs.ravel()))
    extra_a6_relative = _raw_relative(extra_a6_norm, extra_a6_rhs_norm)

    def active_explicit_facts(prefix: str) -> dict[str, float]:
        carrier_norm = float(
            np.linalg.norm(residual_arrays[f"{prefix}_zero_slave_carrier_residual"])
        )
        port_norm = float(
            np.linalg.norm(residual_arrays[f"{prefix}_augmented_port_residual"])
        )
        rhs_norm = float(
            np.linalg.norm(residual_arrays[f"{prefix}_native_A6_effective_rhs"])
        )
        combined_norm = float(np.hypot(carrier_norm, port_norm))
        return {
            "zero_slave_carrier_residual_norm": carrier_norm,
            "port_residual_norm": port_norm,
            "native_effective_rhs_norm": rhs_norm,
            "combined_residual_norm": combined_norm,
            "combined_relative": combined_norm / max(rhs_norm, np.finfo(float).tiny),
        }

    primary_active = active_explicit_facts("primary")
    extra_active = active_explicit_facts("extra_lu")

    residuals = summary["residuals"]
    residual_key = "original_A6_active_rectangle_relative"
    _matches_recorded_value(
        primary_condensed_relative,
        residuals["condensed_direct_relative"],
        label="primary condensed residual ratio",
    )
    _matches_recorded_value(
        primary_a6_relative,
        residuals[residual_key],
        label="primary native A6 residual ratio",
    )
    _matches_recorded_value(
        condensed_rhs_norm,
        primary["condensed_rhs_norm"],
        label="primary condensed RHS norm",
    )
    _matches_recorded_value(
        native_effective_rhs_norm,
        primary["native_A6_effective_rhs_norm"],
        label="primary native A6 effective RHS norm",
    )
    _matches_recorded_value(
        native_effective_rhs_norm,
        residuals["rhs_norm"],
        label="summary native RHS norm (port_rhs=None)",
    )
    _matches_recorded_value(
        native_effective_rhs_norm,
        residuals["native_A6_effective_rhs_norm"],
        label="summary native A6 effective RHS norm",
    )
    _matches_recorded_value(
        primary_active["combined_relative"],
        residuals["full_active_space_explicit_relative"],
        label="primary full active-space explicit residual ratio",
    )
    _matches_recorded_value(
        primary_active["combined_residual_norm"],
        residuals["full_active_space_explicit_residual_norm"],
        label="primary full active-space explicit residual norm",
    )
    _matches_recorded_value(
        primary_active["native_effective_rhs_norm"],
        residuals["full_active_space_explicit_rhs_norm"],
        label="primary full active-space explicit RHS norm",
    )
    primary_active_record = primary["full_active_space_explicit"]
    for field in (
        "zero_slave_carrier_residual_norm",
        "port_residual_norm",
        "combined_residual_norm",
        "native_effective_rhs_norm",
        "combined_relative",
    ):
        _matches_recorded_value(
            primary_active[field],
            primary_active_record[field],
            label=f"primary full active-space explicit {field}",
        )

    correction = extra["linear_correction"]
    _matches_recorded_value(
        primary_condensed_norm,
        correction["initial_explicit_residual_norm"],
        label="extra-LU before residual norm",
    )
    _matches_recorded_value(
        primary_condensed_relative,
        correction["initial_explicit_residual_relative"],
        label="extra-LU before residual ratio",
    )
    _matches_recorded_value(
        condensed_rhs_norm,
        correction["rhs_norm"],
        label="extra-LU condensed RHS norm",
    )
    _matches_recorded_value(
        extra_condensed_norm,
        correction["corrected_explicit_residual_norm"],
        label="extra-LU after residual norm",
    )
    _matches_recorded_value(
        extra_condensed_relative,
        correction["corrected_explicit_residual_relative"],
        label="extra-LU after residual ratio",
    )
    _matches_recorded_value(
        extra_condensed_relative,
        extra["condensed_residual_relative"],
        label="extra-LU condensed residual ratio",
    )
    _matches_recorded_value(
        extra_a6_relative,
        extra["independent_A6_relative"],
        label="extra-LU native A6 residual ratio",
    )
    _matches_recorded_value(
        extra_a6_rhs_norm,
        extra["native_A6_effective_rhs_norm"],
        label="extra-LU native A6 effective RHS norm",
    )
    extra_active_record = extra["full_active_space_explicit"]
    for endpoint, raw_facts in (("before", primary_active), ("after", extra_active)):
        for field in (
            "zero_slave_carrier_residual_norm",
            "port_residual_norm",
            "combined_residual_norm",
            "native_effective_rhs_norm",
            "combined_relative",
        ):
            _matches_recorded_value(
                raw_facts[field],
                extra_active_record[endpoint][field],
                label=f"extra-LU {endpoint} full active-space explicit {field}",
            )
    _matches_recorded_value(
        primary_active["combined_relative"],
        extra_active_record["before"]["combined_relative"],
        label="extra-LU before full active-space explicit ratio",
    )
    _matches_recorded_value(
        extra_active["combined_relative"],
        extra_active_record["after"]["combined_relative"],
        label="extra-LU after full active-space explicit ratio",
    )
    _matches_recorded_value(
        primary_active["combined_residual_norm"],
        extra_active_record["before"]["combined_residual_norm"],
        label="extra-LU before full active-space explicit norm",
    )
    _matches_recorded_value(
        extra_active["combined_residual_norm"],
        extra_active_record["after"]["combined_residual_norm"],
        label="extra-LU after full active-space explicit norm",
    )

    condensed_b_minus_ax_strict_decrease = bool(
        extra_condensed_norm < primary_condensed_norm
        and extra_condensed_relative < primary_condensed_relative
    )
    full_active_explicit_strict_decrease = bool(
        np.array_equal(primary_a6_rhs, extra_a6_rhs)
        and extra_active["combined_residual_norm"]
        < primary_active["combined_residual_norm"]
        and extra_active["combined_relative"] < primary_active["combined_relative"]
    )
    _matches_recorded_value(
        float(condensed_b_minus_ax_strict_decrease),
        float(correction.get("condensed_b_minus_ax_strict_decrease")),
        label="extra-LU condensed b-Ax strict-decrease gate",
    )
    _matches_recorded_value(
        float(full_active_explicit_strict_decrease),
        float(extra_active_record.get("strict_decrease")),
        label="extra-LU full active-space strict-decrease gate",
    )
    if extra_active_record.get("same_rhs") is not bool(
        np.array_equal(primary_a6_rhs, extra_a6_rhs)
    ):
        raise ValueError("A2_q recorded full active-space RHS identity is inconsistent")

    primary_output_facts = summary.get("official_result") or summary.get(
        "measured_endpoint_output_not_official"
    )
    if not isinstance(primary_output_facts, dict):
        raise TypeError("A2_q summary lacks raw primary endpoint outputs")
    primary_output = _raw_modal_volume_output(
        label="primary",
        modal_path=Path(str(primary["modal_rows_path"])),
        modal_sha256=str(primary["modal_rows_sha256"]),
        volume_path=Path(str(primary["volume_absorption_path"])),
        volume_sha256=str(primary["volume_absorption_sha256"]),
        output_facts=primary_output_facts,
        physical_sha256=physical_sha,
        discretization_sha256=discretization_sha,
    )
    extra_volume_path = Path(str(extra_files["extra_volume_absorption_path"]))
    extra_output_facts = {
        "electric_finite": bool(
            extra["hard_solver_gates"].get("complete_modal_output_finite")
        ),
        "auxiliary_finite": bool(
            extra["hard_solver_gates"].get("complete_modal_output_finite")
        ),
        "port_metrics": extra["physical_output"],
        "volume_metrics": {
            "A_volume_total": extra["physical_output"]["A_volume_total"]
        },
        "energy_closure_error_port_volume": extra["energy_closure_error_port_volume"],
    }
    extra_output = _raw_modal_volume_output(
        label="extra-LU",
        modal_path=Path(str(extra_files["extra_modal_rows_path"])),
        modal_sha256=str(extra_files["extra_modal_rows_sha256"]),
        volume_path=extra_volume_path,
        volume_sha256=str(extra_files["extra_volume_absorption_sha256"]),
        output_facts=extra_output_facts,
        physical_sha256=physical_sha,
        discretization_sha256=discretization_sha,
    )
    primary_closure = float(primary_output["closure_recomputed_from_rows_and_volume"])
    extra_closure = float(extra_output["closure_recomputed_from_rows_and_volume"])
    raw_gates = {
        "primary_A6_le_1e_8": primary_a6_relative <= 1.0e-8,
        "primary_condensed_le_1e_9": primary_condensed_relative <= 1.0e-9,
        "primary_full_active_space_explicit_le_1e_8": primary_active[
            "combined_relative"
        ]
        <= 1.0e-8,
        "primary_closure_le_1e_5": abs(primary_closure) <= 1.0e-5,
        "normal_correction_recalculated_from_raw": normal_correction_raw["passed"],
        "extra_A6_le_1e_8": extra_a6_relative <= 1.0e-8,
        "extra_condensed_le_1e_9": extra_condensed_relative <= 1.0e-9,
        "extra_full_active_space_explicit_le_1e_8": extra_active["combined_relative"]
        <= 1.0e-8,
        "extra_closure_le_1e_5": abs(extra_closure) <= 1.0e-5,
        "both_outputs_finite_and_complete": bool(
            primary_output["output_finite"]
            and extra_output["output_finite"]
            and primary_output["mode_count"] == 612
            and extra_output["mode_count"] == 612
        ),
    }
    return {
        "schema": "task43.v2.a2_q_raw_hard_gate_recomputation.v1",
        "passed": all(raw_gates.values()),
        "gates": raw_gates,
        "primary": {
            "condensed_residual_norm": primary_condensed_norm,
            "condensed_rhs_norm": condensed_rhs_norm,
            "condensed_relative": primary_condensed_relative,
            "native_A6_residual_norm": primary_a6_norm,
            "native_A6_effective_rhs_norm": native_effective_rhs_norm,
            "native_A6_relative": primary_a6_relative,
            "full_active_space_explicit": primary_active,
            "output": primary_output,
        },
        "extra_lu": {
            "condensed_residual_norm": extra_condensed_norm,
            "condensed_rhs_norm": condensed_rhs_norm,
            "condensed_relative": extra_condensed_relative,
            "native_A6_residual_norm": extra_a6_norm,
            "native_A6_effective_rhs_norm": extra_a6_rhs_norm,
            "native_A6_relative": extra_a6_relative,
            "full_active_space_explicit": extra_active,
            "output": extra_output,
        },
        "extra_lu_uncertainty": {
            "condensed_b_minus_Ax_strict_decrease": condensed_b_minus_ax_strict_decrease,
            "full_active_space_explicit_strict_decrease": full_active_explicit_strict_decrease,
            "primary_full_active_space_explicit": primary_active,
            "extra_full_active_space_explicit": extra_active,
            "passed_strict_decrease_gates": bool(
                condensed_b_minus_ax_strict_decrease
                and full_active_explicit_strict_decrease
            ),
        },
        "normal_correction_recalculated_from_raw": normal_correction_raw,
        "extra_lu_helper_integrity": extra_helper_integrity,
        "native_A6_denominator_definition": (
            "norm(native_effective_rhs), exactly the saved evaluator output for "
            "full_rhs-B*H_p^{-1}*port_rhs; this runner passes port_rhs=None and "
            "rhs_is_mpc_dual=True, so the denominator is not substituted"
        ),
        "summary_status_used_only_as_negative_consistency_check": (
            summary.get("passed") is True
        ),
    }


def _bind_file(relative: Path, expected_sha256: str, *, label: str) -> Path:
    path = (_REPO_ROOT / relative).resolve()
    if not path.is_file() or _sha256(path) != expected_sha256:
        raise ValueError(f"frozen {label} identity changed: {path}")
    return path


def _validate_a2_q_retry_record(
    record: dict[str, Any],
    *,
    actual_summary_sha256: str,
    actual_root_audit_sha256: str,
    actual_launch_identity_sha256: str,
    actual_worker_log_sha256: str,
    summary: dict[str, Any],
    root_audit: dict[str, Any],
    launch_identity: dict[str, Any],
    watchdog_exit_code: int,
    launcher_exit_code: int,
    numerical_output_files: list[str],
) -> None:
    """Validate the one frozen A2_q retry against the consumed launch record."""

    original = record.get("original_frozen_inputs", {})
    if (
        record.get("schema") != "task43.v2.a2_q_single_retry_authorization.v1"
        or record.get("status") != "frozen_before_retry_dispatch"
        or original.get("v2_contract_path") != str(_CONTRACT_REL)
        or original.get("v2_contract_sha256") != _CONTRACT_SHA256
        or original.get("a2_native_contract_path") != str(_A2_NATIVE_CONTRACT_REL)
        or original.get("a2_native_contract_sha256") != _A2_NATIVE_CONTRACT_SHA256
        or original.get("plan_markdown_path") != str(_PLAN_REL)
        or original.get("plan_markdown_sha256") != _PLAN_SHA256
    ):
        raise ValueError("A2_q retry authorization changed its frozen source bindings")
    authorization = record.get("authorization", {})
    if (
        authorization.get("scope") != "one A2_q attempt 2 only"
        or authorization.get("authorization_basis")
        != "existing user authorization counts failures and retries within the fixed budget and freezes adjustments prospectively; this one-time phase allocation is the main controller's execution decision, not a new ChatGPT review approval or a separate user confirmation"
        or authorization.get("attempt_2_uses_remaining_A2_slot") is not True
        or authorization.get("replaces_unused_A2_R_slot") is not True
        or authorization.get("A2_R_status") != "cancelled_not_run"
        or authorization.get("no_A2_R_transition") is not True
        or authorization.get("no_A2_attempt_after_attempt_2") is not True
        or authorization.get("B_C_status") != "locked_by_unqualified_A1_pair"
        or authorization.get("settings_or_numeric_thresholds_changed") is not False
        or authorization.get("original_contract_or_attempt_1_rewritten") is not False
    ):
        raise ValueError(
            "A2_q retry authorization does not enforce its one-attempt scope"
        )

    endpoint = record.get("retry_endpoint", {})
    if (
        endpoint.get("phase") != "A2_q"
        or endpoint.get("attempt") != 2
        or endpoint.get("attempt_root")
        != "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt2"
        or endpoint.get("runner_output_directory")
        != "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt2/run"
        or endpoint.get("watchdog_phase_path")
        != "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt2/watchdog/workflow_phase.json"
        or endpoint.get("volume_quadrature_degree") != 19
        or endpoint.get("incident_and_port_quadrature_degree") != 32
        or endpoint.get("modal_rectangle_max_abs_m_n") != [4, 8]
        or endpoint.get("normal_same_factor_correction_limit") != 2
        or endpoint.get("extra_same_factor_diagnostic_corrections") != 1
        or endpoint.get("resource_profile") != "task43_hp_adaptivity_resource_v1"
        or endpoint.get("whole_watchdog_wall_limit_seconds") != 7200
        or endpoint.get("dynamic_memory_profile_and_zero_task_swap_gate_unchanged")
        is not True
        or endpoint.get(
            "native_complex128_int64_mpi1_cpu1_single_thread_abi_gates_unchanged"
        )
        is not True
        or endpoint.get(
            "original_physics_discretization_residual_energy_and_perturbation_gates_unchanged"
        )
        is not True
        or endpoint.get("this_does_not_restore_A2_R_or_unlock_B_C") is not True
    ):
        raise ValueError("A2_q retry endpoint differs from the frozen A2_q settings")

    budget = record.get("attempt_budget", {})
    if (
        budget.get("max_total") != 6
        or budget.get("A1_quota_max") != 2
        or budget.get("A2_quota_max") != 2
        or budget.get("counts_before_retry")
        != {
            "A1_q_started": 1,
            "A1_R_started": 0,
            "A2_q_started": 1,
            "A2_R_started": 0,
            "B_started": 0,
            "C_started": 0,
            "total_started": 2,
            "remaining": 4,
        }
        or budget.get("counts_after_retry_dispatch")
        != {
            "A1_q_started": 1,
            "A1_R_started": 0,
            "A2_q_started": 2,
            "A2_R_started": 0,
            "B_started": 0,
            "C_started": 0,
            "total_started": 3,
            "remaining": 3,
        }
        or budget.get("unused_A2_R_slot_reallocated_once_to_A2_q") is not True
        or budget.get("no_quota_increase_or_further_redistribution") is not True
        or budget.get("retry_failure_consumes_the_final_A2_slot") is not True
    ):
        raise ValueError(
            "A2_q retry authorization has an invalid actual attempt budget"
        )

    terminal = record.get("consumed_attempt_1", {})
    expected_paths = {
        "attempt_root": "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt1",
        "launch_identity_path": (
            "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt1/launch_identity.json"
        ),
        "watchdog_summary_path": (
            "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt1/watchdog/summary.json"
        ),
        "root_terminal_audit_path": (
            "benchmarks/artifacts/task43/v2_root_audit/a2_q_attempt1_terminal_audit.json"
        ),
    }
    if any(terminal.get(key) != value for key, value in expected_paths.items()):
        raise ValueError("A2_q retry is not bound to the consumed attempt-1 paths")
    if (
        terminal.get("phase") != "A2_q"
        or terminal.get("attempt") != 1
        or terminal.get("source_head") != "a3657ca1f82fbac0b18aead39ad78285b0887c38"
        or terminal.get("launch_identity_sha256") != actual_launch_identity_sha256
        or terminal.get("watchdog_summary_sha256") != actual_summary_sha256
        or terminal.get("root_terminal_audit_sha256") != actual_root_audit_sha256
        or terminal.get("worker_log_sha256") != actual_worker_log_sha256
        or terminal.get("watchdog_classification") != "WORKER_FAILED"
        or terminal.get("watchdog_worker_exit_code") != 1
        or terminal.get("watchdog_process_tree_cleared") is not True
        or terminal.get("launcher_exit_code") != 2
        or terminal.get("failure_classification")
        != "infrastructure_entry_failure_before_mesh_or_PDE"
        or terminal.get("numeric_output_files") != []
        or terminal.get("formal_attempt_consumed") is not True
        or summary.get("classification") != "WORKER_FAILED"
        or summary.get("leader_exit_code") != 1
        or summary.get("descendants_cleared") is not True
        or root_audit.get("summary_sha256") != actual_summary_sha256
        or root_audit.get("classification")
        != "FAILED_NATIVE_WATCHDOG_PHASE_PATH_WIRING_BEFORE_MESH_NO_NUMERICAL_RESULT"
        or root_audit.get("formal_attempt_consumed") is not True
        or launch_identity.get("HEAD") != terminal.get("source_head")
        or launch_identity.get("phase") != "A2_q"
        or launch_identity.get("attempt") != 1
        or watchdog_exit_code != 2
        or launcher_exit_code != 2
        or numerical_output_files != []
    ):
        raise ValueError("A2_q retry terminal evidence does not match attempt 1")


def _load_a2_q_retry_authorization() -> dict[str, Any]:
    """Bind the one-time retry record to the actual failed pre-mesh attempt."""

    retry_path = _bind_file(
        _A2_Q_RETRY_REL, _A2_Q_RETRY_SHA256, label="A2_q retry authorization"
    )
    record = _read_json(retry_path)
    terminal = record.get("consumed_attempt_1", {})
    launch_path = _bind_file(
        Path(terminal.get("launch_identity_path", "")),
        str(terminal.get("launch_identity_sha256", "")),
        label="A2_q attempt-1 launch identity",
    )
    summary_path = _bind_file(
        Path(terminal.get("watchdog_summary_path", "")),
        str(terminal.get("watchdog_summary_sha256", "")),
        label="A2_q attempt-1 watchdog summary",
    )
    root_audit_path = _bind_file(
        Path(terminal.get("root_terminal_audit_path", "")),
        str(terminal.get("root_terminal_audit_sha256", "")),
        label="A2_q attempt-1 root terminal audit",
    )
    log_path = (
        _REPO_ROOT / str(terminal.get("attempt_root", "")) / "watchdog/worker.log"
    )
    if not log_path.is_file():
        raise ValueError("A2_q attempt-1 watchdog log is missing")
    worker_log_sha256 = _sha256(log_path)
    worker_log = log_path.read_text(encoding="utf-8")
    launch_identity = _read_json(launch_path)
    summary = _read_json(summary_path)
    root_audit = _read_json(root_audit_path)
    attempt_root = _REPO_ROOT / str(terminal["attempt_root"])
    numerical_directory = attempt_root / "run/numerical_output"
    if not numerical_directory.is_dir():
        raise ValueError("A2_q attempt-1 numerical-output directory is missing")
    numerical_output_files = sorted(
        str(path.relative_to(_REPO_ROOT))
        for path in numerical_directory.rglob("*")
        if path.is_file()
    )
    try:
        watchdog_exit_code = int(
            (attempt_root / "watchdog_exit_code.txt").read_text().strip()
        )
        launcher_exit_code = int(
            (attempt_root / "launcher_exit_code.txt").read_text().strip()
        )
    except (OSError, ValueError) as error:
        raise ValueError("A2_q attempt-1 exit-code records are unavailable") from error
    if "requires the native-capacity watchdog" not in worker_log:
        raise ValueError("A2_q attempt-1 worker log lacks its recorded entry failure")
    _validate_a2_q_retry_record(
        record,
        actual_summary_sha256=_sha256(summary_path),
        actual_root_audit_sha256=_sha256(root_audit_path),
        actual_launch_identity_sha256=_sha256(launch_path),
        actual_worker_log_sha256=worker_log_sha256,
        summary=summary,
        root_audit=root_audit,
        launch_identity=launch_identity,
        watchdog_exit_code=watchdog_exit_code,
        launcher_exit_code=launcher_exit_code,
        numerical_output_files=numerical_output_files,
    )
    return {
        "path": str(retry_path),
        "sha256": _A2_Q_RETRY_SHA256,
        "record": record,
    }


def _validate_y6_recovered_bundle_binding(
    identity: dict[str, Any], expected_path: Path, expected_sha256: str
) -> None:
    """Bind the imported Y6 bundle through its actual restore-identity field."""

    recovered_bundle = identity.get("recovered_bundle", {})
    recorded_path = recovered_bundle.get("path")
    recorded_sha256 = recovered_bundle.get("sha256")
    if (
        not isinstance(recorded_path, str)
        or not recorded_path
        or Path(recorded_path).resolve() != expected_path.resolve()
        or recorded_sha256 != expected_sha256
    ):
        raise ValueError(
            "Y6_1 restore identity does not bind the frozen recovered-space bundle"
        )


def _validate_v2_y6_native_profile_payload(
    resolved_payload: dict[str, Any],
    *,
    raw_path: str,
    raw_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate an in-memory V2 copy while preserving the immutable Y6 input."""

    from src.io.native_capacity_profile import (
        native_capacity_profile_identity,
        native_profile_facts,
    )
    from src.io.resolved_config import canonical_json_bytes
    from src.runners.p6_condensed_direct import _validate_resolved_profile

    expected_identity = "task40para_phi90_13p5_D15_Y6_1_p6_direct_v1"
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not isinstance(raw_sha256, str)
        or len(raw_sha256) != 64
        or any(character not in "0123456789abcdef" for character in raw_sha256)
    ):
        raise ValueError("V2 Y6 profile binding lacks a valid raw input identity")

    normalized_payload = copy.deepcopy(resolved_payload)
    method = normalized_payload.get("method")
    solver = normalized_payload.get("solver")
    derived = normalized_payload.get("derived")
    if not isinstance(method, dict) or not isinstance(solver, dict):
        raise TypeError("V2 Y6 profile input lacks method or solver identity")
    if not isinstance(derived, dict):
        raise TypeError("V2 Y6 profile input lacks derived facts")
    identity = native_capacity_profile_identity(method.get("kind"), solver)
    if identity != expected_identity:
        raise ValueError(
            "V2 profile compatibility is restricted to the frozen Y6_1 route"
        )
    actual_facts = derived.get("native_capacity_profile")
    if not isinstance(actual_facts, dict):
        raise TypeError("V2 Y6 resolved native profile facts are missing")

    expected_facts = native_profile_facts(identity)
    actual_mesh = actual_facts.get("component_options", {}).get(
        "directional_mesh_comparison"
    )
    expected_mesh = expected_facts.get("component_options", {}).get(
        "directional_mesh_comparison"
    )
    if not isinstance(actual_mesh, dict) or not isinstance(expected_mesh, dict):
        raise TypeError("V2 Y6 directional mesh profile facts are missing")
    expected_label = expected_mesh.get("display_label")
    if not isinstance(expected_label, str) or not expected_label:
        raise ValueError("current Y6 profile lacks its expected display label")

    normalization_status = "already_matches_current_profile"
    if "display_label" not in actual_mesh:
        actual_mesh["display_label"] = expected_label
        normalization_status = "missing_display_label_added_to_in_memory_copy"
    elif actual_mesh["display_label"] != expected_label:
        raise ValueError(
            "V2 Y6 profile compatibility rejects an incorrect display_label"
        )

    if canonical_json_bytes(actual_facts) != canonical_json_bytes(expected_facts):
        raise ValueError(
            "V2 Y6 profile differs from the native profile beyond display_label compatibility"
        )

    validated_facts = _validate_resolved_profile(normalized_payload)
    raw_facts = resolved_payload["derived"]["native_capacity_profile"]
    report = {
        "schema": "task43.v2.y6_native_profile_compatibility.v1",
        "raw_resolved_config_path": raw_path,
        "raw_resolved_config_sha256": raw_sha256,
        "raw_profile_identity": identity,
        "raw_profile_facts_sha256": hashlib.sha256(
            canonical_json_bytes(raw_facts)
        ).hexdigest(),
        "native_validator": "src.runners.p6_condensed_direct._validate_resolved_profile",
        "native_validator_passed_on_in_memory_copy": True,
        "normalization_status": normalization_status,
        "normalized_field": (
            "derived.native_capacity_profile.component_options."
            "directional_mesh_comparison.display_label"
        ),
        "raw_field_value": resolved_payload["derived"]["native_capacity_profile"][
            "component_options"
        ]["directional_mesh_comparison"].get("display_label", "<missing>"),
        "normalized_field_value": expected_label,
        "normalized_profile_facts_sha256": hashlib.sha256(
            canonical_json_bytes(validated_facts)
        ).hexdigest(),
        "numeric_resource_and_solver_profile_facts_unchanged": True,
    }
    return normalized_payload, report


def _validate_a2_native_contract_copy(
    original: dict[str, Any], a2_contract: dict[str, Any]
) -> None:
    """Allow only the scoped A2 native correction-interface clarification."""

    applicability = a2_contract.get("a2_native_applicability", {})
    if (
        applicability.get("scope") != ["A2_q", "A2_R"]
        or applicability.get("effective_before_any_A2_attempt") is not True
        or applicability.get("does_not_apply_to") != ["A1_q", "A1_R", "B", "C"]
        or applicability.get("original_contract_path") != str(_CONTRACT_REL)
        or applicability.get("original_contract_sha256") != _CONTRACT_SHA256
        or applicability.get("original_plan_markdown_path") != str(_PLAN_REL)
        or applicability.get("original_plan_markdown_sha256") != _PLAN_SHA256
    ):
        raise ValueError("A2 native contract applicability or original binding changed")
    normal_interface = applicability.get("normal_correction_interface", {})
    if not all(
        isinstance(normal_interface.get(key), str) and normal_interface[key]
        for key in ("A1_KSP", "A2_native_PETSc_MatSolve", "rationale")
    ):
        raise ValueError("A2 native contract lacks its interface-specific conditions")
    a2_base = copy.deepcopy(a2_contract)
    a2_base.pop("a2_native_applicability", None)
    try:
        a2_base["hard_solver_gates"]["normal_correction_recalculated_from_raw"] = (
            original["hard_solver_gates"]["normal_correction_recalculated_from_raw"]
        )
    except (KeyError, TypeError) as error:
        raise ValueError("A2 native contract lacks the original normal gate") from error
    if a2_base != original:
        raise ValueError(
            "A2 native contract changed settings outside its scoped interface clarification"
        )


def _require_a2_budget_frozen_before_attempt(a2_contract: dict[str, Any]) -> None:
    """Reject the pending proposal until actual A1 pair costs are frozen."""

    applicability = a2_contract.get("a2_native_applicability", {})
    budget = applicability.get("actual_attempt_budget_at_A2_freeze", {})
    counts = budget.get("counts_at_A2_freeze", {})
    phase_keys = (
        "A1_q_started",
        "A1_R_started",
        "A2_q_started",
        "A2_R_started",
        "B_started",
        "C_started",
    )
    if budget.get("status") != "frozen_before_A2":
        raise ValueError(
            "A2 is locked until the actual attempt budget is frozen after the A1 pair"
        )
    if any(type(counts.get(key)) is not int or counts[key] < 0 for key in phase_keys):
        raise ValueError("A2 frozen attempt budget has invalid phase counts")
    total_max = counts.get("total_max")
    total_started = counts.get("total_started")
    remaining = counts.get("remaining")
    if (
        type(total_max) is not int
        or total_max != 6
        or type(total_started) is not int
        or type(remaining) is not int
        or total_started != sum(counts[key] for key in phase_keys)
        or total_started > total_max
        or remaining != total_max - total_started
        or any(counts[key] != 0 for key in phase_keys[2:])
        or counts["A1_q_started"] != 1
        or counts["A1_R_started"] not in (0, 1)
        or counts["A1_q_started"] + counts["A1_R_started"] > 2
    ):
        raise ValueError(
            "A2 frozen attempt budget is inconsistent, over A1 quota, or already spent"
        )

    def require_terminal_binding(key: str, expected_phase: str) -> None:
        binding = budget.get(key, {})
        digest = binding.get("terminal_summary_sha256")
        if (
            binding.get("phase") != expected_phase
            or not isinstance(binding.get("attempt_path"), str)
            or not binding["attempt_path"]
            or binding.get("terminal_status") in (None, "", "running", "unknown")
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(
                f"A2 frozen attempt budget lacks terminal {expected_phase} evidence"
            )

    require_terminal_binding("latest_A1_q_attempt_binding", "A1_q")
    if counts["A1_R_started"]:
        require_terminal_binding("latest_A1_R_attempt_binding", "A1_R")


def _validate_frozen_inputs(phase: str) -> tuple[dict[str, Any], dict[str, Any]]:
    contract_path = _bind_file(_CONTRACT_REL, _CONTRACT_SHA256, label="V2 contract")
    a2_contract_path = _bind_file(
        _A2_NATIVE_CONTRACT_REL,
        _A2_NATIVE_CONTRACT_SHA256,
        label="A2 native interface contract",
    )
    plan_path = _bind_file(_PLAN_REL, _PLAN_SHA256, label="V2 plan")
    contract = _read_json(contract_path)
    a2_contract = _read_json(a2_contract_path)
    _validate_a2_native_contract_copy(contract, a2_contract)
    _require_a2_budget_frozen_before_attempt(a2_contract)
    if (
        contract.get("schema") != "task43.v2.finite_diagnostic_contract.v2"
        or contract.get("status") != "frozen_for_execution"
        or contract.get("formal_model_attempts", {}).get("total_max") != 6
        or contract.get("formal_model_attempts", {}).get("current_v2_formal_models_run")
        != 0
    ):
        raise ValueError(
            "frozen Task43 V2 contract no longer matches its authorized state"
        )

    input_path = _bind_file(
        _Y6_ROOT / "resolved_config.json", _Y6_INPUT_SHA256, label="Y6_1 resolved input"
    )
    summary_path = _bind_file(
        _Y6_ROOT / "p6_condensed_direct_summary.json",
        _Y6_SUMMARY_SHA256,
        label="Y6_1 original direct summary",
    )
    rows_path = _bind_file(
        _Y6_ROOT / "numerical_output/dtn_port_diffraction_orders_3d.json",
        _Y6_ROWS_SHA256,
        label="Y6_1 original R13 rows",
    )
    space_bundle_path = _bind_file(
        _Y6_ROOT / "recovered_reference_bundle.npz",
        _Y6_BUNDLE_SHA256,
        label="Y6_1 recovered space bundle",
    )
    identity_path = _bind_file(
        _Y6_ROOT / "restore_identity_record.json",
        _Y6_IDENTITY_SHA256,
        label="Y6_1 restore identity record",
    )
    old_summary = _read_json(summary_path)
    old_identity = _read_json(identity_path)
    if (
        old_summary.get("source_sha") != "6320ae621ddf94d39e9006628a5ef68b0dfdfffe"
        or old_summary.get("profile") != "task40para_phi90_13p5_D15_Y6_1_p6_direct_v1"
        or old_summary.get("passed") is not True
        or old_summary.get("operator_identity", {}).get("volume_quadrature_metadata")
        != [
            {"quadrature_degree": 15, "quadrature_rule": "default"},
            {"quadrature_degree": 15, "quadrature_rule": "default"},
        ]
        or old_summary.get("mode_inventory", {}).get("active_mode_count") != 612
        or old_identity.get("label") != "Y6_1"
        or old_identity.get("source_sha") != "6320ae621ddf94d39e9006628a5ef68b0dfdfffe"
    ):
        raise ValueError("Y6_1 frozen q15/q28/R13 baseline identity is incomplete")
    _validate_y6_recovered_bundle_binding(
        old_identity, space_bundle_path, _Y6_BUNDLE_SHA256
    )

    sample_paths = {
        "q8": Path(
            "benchmarks/artifacts/task43/round1_candidates/comparisons/"
            "post_selection_joint_attempt1/post_selection_shared_q8.npz"
        ),
        "q10": Path(
            "benchmarks/artifacts/task43/round1_candidates/comparisons/"
            "post_selection_joint_attempt1/post_selection_shared_q10.npz"
        ),
    }
    sample_hashes = {"q8": _Q8_SAMPLES_SHA256, "q10": _Q10_SAMPLES_SHA256}
    sample_specs: dict[str, dict[str, str]] = {}
    for order, relative in sample_paths.items():
        sample_path = _bind_file(
            relative, sample_hashes[order], label=f"Y6_1 {order} samples"
        )
        points_key = "points_nm"
        weights_key = "weights_nm3"
        e_key = "Y6_1_E"
        curl_key = "Y6_1_curl_E"
        with np.load(sample_path, allow_pickle=False) as samples:
            expected_count = 516096 if order == "q8" else 1008000
            if (
                points_key not in samples
                or weights_key not in samples
                or e_key not in samples
                or curl_key not in samples
                or samples[points_key].shape != (expected_count, 3)
                or samples[weights_key].shape != (expected_count,)
                or samples[e_key].shape != (expected_count, 3)
                or samples[curl_key].shape != (expected_count, 3)
            ):
                raise ValueError(f"frozen Y6_1 {order} sample schema or count changed")
        sample_specs[order] = {
            "path": str(sample_path),
            "sha256": sample_hashes[order],
            "points_key": points_key,
            "weights_key": weights_key,
            "electric_key": e_key,
            "curl_key": curl_key,
        }

    audit_values: dict[str, tuple[Path, str]] = {}
    audit_documents: dict[str, dict[str, Any]] = {}
    for name, (relative, digest) in _ROOT_AUDITS.items():
        path = _bind_file(relative, digest, label=f"root A2 {name} audit")
        audit_values[name] = (path, digest)
        audit_documents[name] = _read_json(path)
    continuity = audit_documents["source_continuity"]
    axis = audit_documents["axis_profile"]
    modes = audit_documents["mode_policy"]
    if (
        continuity.get("baseline_source_sha") != old_summary.get("source_sha")
        or continuity.get("classification")
        != "read_only_static_source_continuity_evidence_not_PDE_or_complete_dependency_proof"
        or axis.get("axis_Y6_1_old_current_exactly_equal") is not True
        or axis.get("only_profile_change_is_display_label") is not True
        or modes.get("old_current_all_612_modes_every_dataclass_field_exactly_equal")
        is not True
        or modes.get("effective_legacy_rectangle") != [4, 8]
        or modes.get("effective_surface_q") != 28
        or modes.get("effective_legacy_scale_policy") is not None
    ):
        raise ValueError(
            "root A2 source/axis/mode continuity evidence does not meet the frozen scope"
        )

    repository_source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError(
            "Task43 A2 requires committed, clean source before its model attempt"
        )

    if phase == "A2_R":
        previous_dir = (
            _REPO_ROOT / "benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt1"
        ) / "run"
        previous_summary_path = previous_dir / "p6_condensed_direct_summary.json"
        previous_comparison_path = previous_dir / "comparison_record.json"
        if (
            not previous_summary_path.is_file()
            or not previous_comparison_path.is_file()
        ):
            raise ValueError(
                "A2_R requires the completed A2_q endpoint and its comparison record"
            )
        previous_summary = _read_json(previous_summary_path)
        previous_comparison = _read_json(previous_comparison_path)
        _require_a2_q_r13_same_source_identity(previous_summary, repository_source)
        comparison_binding = previous_summary.get("task43_v2_comparison", {})
        if str(Path(str(comparison_binding.get("path", ""))).resolve()) != str(
            previous_comparison_path.resolve()
        ) or comparison_binding.get("sha256") != _sha256(previous_comparison_path):
            raise ValueError("A2_q comparison file is not bound by its summary hash")
        if (
            previous_comparison.get("phase") != "A2_q"
            or previous_comparison.get("contract_sha256") != _CONTRACT_SHA256
            or previous_comparison.get("a2_native_contract_sha256")
            != _A2_NATIVE_CONTRACT_SHA256
            or previous_comparison.get("plan_markdown_sha256") != _PLAN_SHA256
            or previous_comparison.get("source_sha") != repository_source
        ):
            raise ValueError("A2_q comparison does not bind the frozen A2 contracts")
        raw_hard_gate = _recompute_a2_q_raw_hard_gates(
            previous_summary_path, previous_summary
        )
        if (
            previous_summary.get("passed") is not True
            or raw_hard_gate.get("passed") is not True
            or previous_comparison.get("hard_solver_gate")
            is not raw_hard_gate.get("passed")
            or comparison_binding.get("hard_solver_gate")
            is not raw_hard_gate.get("passed")
        ):
            raise ValueError(
                "A2_R requires A2_q raw residual/rows/closure recomputation to pass; recorded PASS fields are consistency checks only"
            )
        if (
            previous_summary.get("task43_v2_endpoint_identity", {}).get("phase")
            != "A2_q"
        ):
            raise ValueError("A2_R reference endpoint is not an A2_q endpoint")
        sample_facts = previous_summary.get("task43_v2_primary_endpoint_output", {})
        sample_path = Path(str(sample_facts.get("field_samples_path", "")))
        sample_sha = sample_facts.get("field_samples_sha256")
        if not sample_path.is_file() or _sha256(sample_path) != sample_sha:
            raise ValueError(
                "A2_R q8/q10 reference samples do not match completed A2_q output"
            )
        sample_specs = {
            order: {
                "path": str(sample_path),
                "sha256": str(sample_sha),
                "points_key": f"q{int(order[1:])}_points_nm",
                "weights_key": f"q{int(order[1:])}_weights_nm3",
                "electric_key": f"q{int(order[1:])}_E_total_code",
                "curl_key": f"q{int(order[1:])}_curl_E_total_code",
            }
            for order in ("q8", "q10")
        }
        reference = {
            "kind": "prior_A2_q_primary_endpoint",
            "summary_path": str(previous_summary_path),
            "summary_sha256": _sha256(previous_summary_path),
            "comparison_path": str(previous_comparison_path),
            "comparison_sha256": _sha256(previous_comparison_path),
            "modal_rows_path": str(
                previous_dir / "numerical_output/dtn_port_diffraction_orders_3d.json"
            ),
            "modal_rows_sha256": _sha256(
                previous_dir / "numerical_output/dtn_port_diffraction_orders_3d.json"
            ),
            "volume_absorption_path": str(
                previous_dir / "numerical_output/volume_absorption.json"
            ),
            "volume_absorption_sha256": _sha256(
                previous_dir / "numerical_output/volume_absorption.json"
            ),
            "physical_configuration_sha256": previous_summary[
                "task43_v2_endpoint_identity"
            ]["physical_configuration_sha256"],
            "discretization_sha256": previous_summary["task43_v2_endpoint_identity"][
                "discretization_sha256"
            ],
            "A_volume_total": float(
                previous_summary["official_result"]["volume_metrics"]["A_volume_total"]
                if "official_result" in previous_summary
                else previous_summary["measured_endpoint_output_not_official"][
                    "volume_metrics"
                ]["A_volume_total"]
            ),
            "raw_hard_gate_recomputation": raw_hard_gate,
        }
    else:
        reference = {
            "kind": "frozen_original_Y6_1_q15_q28_R13",
            "summary_path": str(summary_path),
            "summary_sha256": _Y6_SUMMARY_SHA256,
            "modal_rows_path": str(rows_path),
            "modal_rows_sha256": _Y6_ROWS_SHA256,
            "volume_absorption_path": None,
            "volume_absorption_sha256": None,
            "physical_configuration_sha256": None,
            "discretization_sha256": None,
            "A_volume_total": float(
                old_summary["official_result"]["volume_metrics"]["A_volume_total"]
            ),
        }

    diagnostic = {
        "schema": "task43.v2.native_p6_diagnostic.v1",
        "phase": phase,
        "volume_quadrature_degree": 19,
        "surface_quadrature_degree": 32,
        "normal_correction_limit": 2,
        "extra_correction_limit": 1,
        "contract_path": str(contract_path),
        "contract_sha256": _CONTRACT_SHA256,
        "a2_native_contract_path": str(a2_contract_path),
        "a2_native_contract_sha256": _A2_NATIVE_CONTRACT_SHA256,
        "plan_markdown_path": str(plan_path),
        "plan_markdown_sha256": _PLAN_SHA256,
        "reference_space_bundle_path": str(space_bundle_path),
        "reference_space_bundle_sha256": _Y6_BUNDLE_SHA256,
        "reference_space_identity_path": str(identity_path),
        "reference_space_identity_sha256": _Y6_IDENTITY_SHA256,
        "field_reference_samples": sample_specs,
        "root_source_continuity_audit_path": str(audit_values["source_continuity"][0]),
        "root_source_continuity_audit_sha256": audit_values["source_continuity"][1],
        "root_axis_profile_audit_path": str(audit_values["axis_profile"][0]),
        "root_axis_profile_audit_sha256": audit_values["axis_profile"][1],
        "root_mode_policy_audit_path": str(audit_values["mode_policy"][0]),
        "root_mode_policy_audit_sha256": audit_values["mode_policy"][1],
        "reference": reference,
        "current_source_sha": repository_source,
        "reference_resolved_config_path": str(input_path),
        "reference_resolved_config_sha256": _Y6_INPUT_SHA256,
        "reference_rows_path": str(rows_path),
    }
    raw_resolved_payload = _read_json(input_path)
    resolved_payload, resolved_profile_compatibility = (
        _validate_v2_y6_native_profile_payload(
            raw_resolved_payload,
            raw_path=str(input_path),
            raw_sha256=_Y6_INPUT_SHA256,
        )
    )
    diagnostic["resolved_profile_compatibility"] = resolved_profile_compatibility
    return diagnostic, {
        "resolved_payload": resolved_payload,
        "resolved_profile_compatibility": resolved_profile_compatibility,
        "old_summary": old_summary,
        "a2_native_contract": a2_contract,
    }


def _load_field_bundle(
    path: Path,
    order: int,
    spec: dict[str, str],
    *,
    cfg: Any,
    physical_sha256: str,
) -> dict[str, Any]:
    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
    )
    from src.postprocessing.physical_field_comparison import (
        magnetic_field_from_electric_curl,
        scattered_field_samples,
    )

    if not path.is_file() or _sha256(path) != spec["sha256"]:
        raise ValueError(f"q{order} comparison input changed: {path}")
    with np.load(path, allow_pickle=False) as arrays:
        points = np.asarray(arrays[spec["points_key"]], dtype=np.float64).copy()
        weights = np.asarray(arrays[spec["weights_key"]], dtype=np.float64).copy()
        electric = np.asarray(arrays[spec["electric_key"]], dtype=np.complex128).copy()
        curl = np.asarray(arrays[spec["curl_key"]], dtype=np.complex128).copy()
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or points.shape[0] == 0
        or weights.shape != (points.shape[0],)
        or electric.shape != (points.shape[0], 3)
        or curl.shape != (points.shape[0], 3)
        or not all(
            np.isfinite(array).all() for array in (points, weights, electric, curl)
        )
        or np.any(weights <= 0.0)
    ):
        raise ValueError(f"q{order} field bundle contains invalid arrays")
    magnetic = magnetic_field_from_electric_curl(
        curl,
        magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
        k0_per_nm=cfg.k0,
        mu_r=cfg.mu_r,
    )
    background_e = np.asarray(
        electric_field_code_values(cfg, points), dtype=np.complex128
    )
    background_h = np.asarray(
        cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(cfg, points),
        dtype=np.complex128,
    )
    return {
        "physical_configuration_identity_sha256": physical_sha256,
        "points_nm": points,
        "weights_nm3": weights,
        "E_total_code": electric,
        "curl_E_total_code": curl,
        "H_total_A_per_m": np.asarray(magnetic, dtype=np.complex128),
        "incident_background_E_code": background_e,
        "incident_background_H_A_per_m": background_h,
        "E_scattered_code": scattered_field_samples(electric, background_e),
        "H_scattered_A_per_m": scattered_field_samples(magnetic, background_h),
    }


def _endpoint_sample_spec(
    path: Path, sample_facts: dict[str, Any], order: int
) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": str(sample_facts["sha256"]),
        "points_key": f"q{order}_points_nm",
        "weights_key": f"q{order}_weights_nm3",
        "electric_key": f"q{order}_E_total_code",
        "curl_key": f"q{order}_curl_E_total_code",
    }


def _comparison_record(
    phase: str,
    run_dir: Path,
    runner_summary: dict[str, Any],
    diagnostic: dict[str, Any],
    old_summary: dict[str, Any],
) -> dict[str, Any]:
    from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
        R13_MODE_KEYS,
        R14_MODE_KEYS,
        compare_field_sample_bundles,
        compare_r13_modal_outputs,
        compare_r13_r14_modal_outputs,
    )
    from src.io.input_validation import simulation_config_3d_from_normalized

    identity = runner_summary["task43_v2_endpoint_identity"]
    physical_sha = str(identity["physical_configuration_sha256"])
    discretization_sha = str(identity["discretization_sha256"])
    cfg = simulation_config_3d_from_normalized(
        _read_json(Path(diagnostic["reference_resolved_config_path"]))
    )
    reference = diagnostic["reference"]
    new_rows_path = Path(
        runner_summary["task43_v2_primary_endpoint_output"]["modal_rows_path"]
    )
    extra = runner_summary["task43_v2_extra_lu_diagnostic"]
    extra_sample_facts = extra["field_samples"]
    primary_sample_path = Path(extra_sample_facts["primary_path"])
    extra_sample_path = Path(extra_sample_facts["extra_lu_path"])
    new_rows_sha = _sha256(new_rows_path)
    if (
        new_rows_sha
        != runner_summary["task43_v2_primary_endpoint_output"]["modal_rows_sha256"]
    ):
        raise ValueError("Task43 A2 primary modal output changed before comparison")

    reference_rows_path = Path(reference["modal_rows_path"])
    if _sha256(reference_rows_path) != reference["modal_rows_sha256"]:
        raise ValueError("Task43 A2 modal reference changed before comparison")
    reference_payload = _read_json(reference_rows_path)
    candidate_payload = _read_json(new_rows_path)
    primary_output_facts = runner_summary.get("official_result") or runner_summary.get(
        "measured_endpoint_output_not_official"
    )
    if not isinstance(primary_output_facts, dict):
        raise TypeError("Task43 A2 summary lacks primary endpoint output facts")
    candidate_a_volume = float(primary_output_facts["volume_metrics"]["A_volume_total"])
    if phase == "A2_q":
        reference_discretization = discretization_sha
        primary_modal = compare_r13_modal_outputs(
            reference_payload,
            candidate_payload,
            reference_a_volume=float(reference["A_volume_total"]),
            candidate_a_volume=candidate_a_volume,
            reference_physical_configuration_sha256=physical_sha,
            candidate_physical_configuration_sha256=physical_sha,
            reference_discretization_sha256=reference_discretization,
            candidate_discretization_sha256=discretization_sha,
            expected_keys=R13_MODE_KEYS,
        )
    else:
        if (
            str(reference.get("physical_configuration_sha256")) != physical_sha
            or str(reference.get("discretization_sha256")) != discretization_sha
        ):
            raise ValueError(
                "A2_R reference and candidate do not share the frozen physical and native P6 identities"
            )
        primary_modal = compare_r13_r14_modal_outputs(
            reference_payload,
            candidate_payload,
            r13_a_volume=float(reference["A_volume_total"]),
            r14_a_volume=candidate_a_volume,
            r13_physical_configuration_sha256=physical_sha,
            r14_physical_configuration_sha256=physical_sha,
            r13_discretization_sha256=str(reference["discretization_sha256"]),
            r14_discretization_sha256=discretization_sha,
        )

    field_comparisons: dict[str, Any] = {}
    for order in (8, 10):
        key = f"q{order}"
        reference_spec = diagnostic["field_reference_samples"][key]
        reference_bundle = _load_field_bundle(
            Path(reference_spec["path"]),
            order,
            reference_spec,
            cfg=cfg,
            physical_sha256=physical_sha,
        )
        candidate_spec = _endpoint_sample_spec(
            primary_sample_path,
            {"sha256": extra_sample_facts["primary_sha256"]},
            order,
        )
        candidate_bundle = _load_field_bundle(
            primary_sample_path,
            order,
            candidate_spec,
            cfg=cfg,
            physical_sha256=physical_sha,
        )
        volume = float(
            cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min)
        )
        field_comparisons[key] = compare_field_sample_bundles(
            reference_bundle,
            candidate_bundle,
            k0_per_nm=float(cfg.k0),
            magnetic_field_scale_A_per_m=float(cfg.magnetic_field_scale_A_per_m),
            mu_r=cfg.mu_r,
            incident_e_norm_floor=float(np.sqrt(volume)),
            incident_h_norm_floor=float(
                cfg.magnetic_field_scale_A_per_m * np.sqrt(volume)
            ),
            incident_g_norm_floor=float(np.sqrt(2.0 * volume)),
        )

    before_rows_path = new_rows_path
    after_rows_path = Path(extra_sample_facts["extra_modal_rows_path"])
    if _sha256(after_rows_path) != extra_sample_facts["extra_modal_rows_sha256"]:
        raise ValueError("Task43 A2 extra-LU modal output changed before comparison")
    before_payload = _read_json(before_rows_path)
    after_payload = _read_json(after_rows_path)
    before_volume_path = Path(
        runner_summary["task43_v2_primary_endpoint_output"]["volume_absorption_path"]
    )
    after_volume_path = Path(extra_sample_facts["extra_volume_absorption_path"])
    if (
        _sha256(before_volume_path)
        != runner_summary["task43_v2_primary_endpoint_output"][
            "volume_absorption_sha256"
        ]
        or _sha256(after_volume_path)
        != extra_sample_facts["extra_volume_absorption_sha256"]
    ):
        raise ValueError(
            "Task43 A2 same-LU volume absorption file changed before comparison"
        )
    before_a_volume = float(_read_json(before_volume_path)["A_volume_total"])
    after_a_volume = float(_read_json(after_volume_path)["A_volume_total"])
    expected_keys = R13_MODE_KEYS if phase == "A2_q" else R14_MODE_KEYS
    extra_modal = compare_r13_modal_outputs(
        before_payload,
        after_payload,
        reference_a_volume=before_a_volume,
        candidate_a_volume=after_a_volume,
        reference_physical_configuration_sha256=physical_sha,
        candidate_physical_configuration_sha256=physical_sha,
        reference_discretization_sha256=discretization_sha,
        candidate_discretization_sha256=discretization_sha,
        expected_keys=expected_keys,
    )
    extra_field_comparisons: dict[str, Any] = {}
    for order in (8, 10):
        key = f"q{order}"
        before_spec = _endpoint_sample_spec(
            primary_sample_path,
            {"sha256": extra_sample_facts["primary_sha256"]},
            order,
        )
        after_spec = _endpoint_sample_spec(
            extra_sample_path,
            {"sha256": extra_sample_facts["extra_lu_sha256"]},
            order,
        )
        before_bundle = _load_field_bundle(
            primary_sample_path,
            order,
            before_spec,
            cfg=cfg,
            physical_sha256=physical_sha,
        )
        after_bundle = _load_field_bundle(
            extra_sample_path, order, after_spec, cfg=cfg, physical_sha256=physical_sha
        )
        volume = float(
            cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min)
        )
        extra_field_comparisons[key] = compare_field_sample_bundles(
            before_bundle,
            after_bundle,
            k0_per_nm=float(cfg.k0),
            magnetic_field_scale_A_per_m=float(cfg.magnetic_field_scale_A_per_m),
            mu_r=cfg.mu_r,
            incident_e_norm_floor=float(np.sqrt(volume)),
            incident_h_norm_floor=float(
                cfg.magnetic_field_scale_A_per_m * np.sqrt(volume)
            ),
            incident_g_norm_floor=float(np.sqrt(2.0 * volume)),
        )

    residuals = runner_summary["residuals"]
    residual_key = "original_A6_active_rectangle_relative"
    residual_bundle_path = Path(
        runner_summary["task43_v2_primary_endpoint_output"][
            "same_lu_residual_vectors_path"
        ]
    )
    residual_arrays = _read_a2_residual_vectors(residual_bundle_path, runner_summary)
    normal_correction_raw = _recompute_a2_normal_correction_gate(
        runner_summary, residual_arrays
    )
    extra_helper_integrity = _recompute_a2_extra_lu_helper_integrity(
        runner_summary, residual_arrays
    )
    primary_hard_gates = {
        "runner_passed": runner_summary.get("passed") is True,
        "full_explicit_A6_le_1e_8": bool(
            np.isfinite(float(residuals[residual_key]))
            and 0.0 <= float(residuals[residual_key]) <= 1.0e-8
        ),
        "condensed_residual_le_1e_9": bool(
            np.isfinite(float(residuals["condensed_direct_relative"]))
            and 0.0 <= float(residuals["condensed_direct_relative"]) <= 1.0e-9
        ),
        "full_active_space_explicit_le_1e_8": bool(
            np.isfinite(float(residuals["full_active_space_explicit_relative"]))
            and 0.0 <= float(residuals["full_active_space_explicit_relative"]) <= 1.0e-8
        ),
        "closure_le_1e_5": bool(
            abs(float(primary_output_facts["energy_closure_error_port_volume"]))
            <= 1.0e-5
        ),
        "normal_correction_recalculated_from_raw": normal_correction_raw["passed"],
    }
    extra_hard_gates = dict(extra["hard_solver_gates"])
    extra_hard_gates["energy_closure_le_1e_5"] = bool(
        abs(float(extra["energy_closure_error_port_volume"])) <= 1.0e-5
    )
    extra_linear_correction_status_pass = bool(
        extra["linear_correction"]["status"] == "PASS"
    )
    same_lu_pass = bool(
        extra_linear_correction_status_pass
        and extra_helper_integrity["passed"]
        and extra_modal["pass_10_percent_perturbation_gate"]
        and all(
            result["pass_10_percent_perturbation_gate"]
            for result in extra_field_comparisons.values()
        )
    )
    primary_pass = bool(
        primary_modal["pass_10_percent_perturbation_gate"]
        and all(
            result["pass_10_percent_perturbation_gate"]
            for result in field_comparisons.values()
        )
    )
    hard_pass = all(primary_hard_gates.values()) and all(extra_hard_gates.values())
    normal_correction_audit = runner_summary.get(
        "task43_v2_normal_correction_audit", {}
    )
    normal_correction_qualified = normal_correction_audit.get("passed") is True
    return {
        "schema": "task43.v2.native_y6_1_endpoint_comparison.v1",
        "phase": phase,
        "selection_eligible": False,
        "source_sha": runner_summary.get("source_sha"),
        "contract_sha256": diagnostic["contract_sha256"],
        "a2_native_contract_sha256": diagnostic["a2_native_contract_sha256"],
        "plan_markdown_sha256": diagnostic["plan_markdown_sha256"],
        "physical_configuration_sha256": physical_sha,
        "discretization_sha256": discretization_sha,
        "reference": reference,
        "primary_endpoint": {
            "modal_comparison": primary_modal,
            "q8_q10_field_comparisons": field_comparisons,
            "hard_solver_gates": primary_hard_gates,
            "normal_correction_audit": normal_correction_audit,
            "pass_10_percent_perturbation_gate": primary_pass,
        },
        "extra_same_lu_uncertainty": {
            "linear_correction": extra["linear_correction"],
            "linear_correction_status_pass": extra_linear_correction_status_pass,
            "raw_helper_integrity": extra_helper_integrity,
            "modal_comparison": extra_modal,
            "q8_q10_field_comparisons": extra_field_comparisons,
            "hard_solver_gates": extra_hard_gates,
            "pass_10_percent_output_uncertainty_gate": same_lu_pass,
        },
        "primary_perturbation_gate": primary_pass,
        "hard_solver_gate": hard_pass,
        "normal_correction_recalculated_from_raw": normal_correction_raw,
        "same_group_R_factor_may_continue": bool(phase == "A2_q" and hard_pass),
        "normal_correction_qualification_gate": normal_correction_qualified,
        "endpoint_qualified": bool(
            primary_pass and hard_pass and same_lu_pass and normal_correction_qualified
        ),
        "scope": "same native Task40 Y6_1 P6 space; original native core/source continuation is separately bounded by cited root audits; no variable-p or A1 qualification transfer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("A2_q", "A2_R"), required=True)
    parser.add_argument("--attempt", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--v3-contract", type=Path)
    parser.add_argument("--v3-plan", type=Path)
    parser.add_argument("--resolved-config", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    retry_authorization = None
    v3_diagnostic = None
    if args.phase == "A2_R":
        _load_a2_q_retry_authorization()
        raise ValueError("A2_R was cancelled by the frozen A2_q retry authorization")
    if args.attempt == 2:
        if args.phase != "A2_q":
            raise ValueError("attempt 2 is frozen for A2_q only")
        if args.v3_contract is not None or args.v3_plan is not None:
            raise ValueError("V3 contract arguments are reserved for A2_q attempt 3")
        retry_authorization = _load_a2_q_retry_authorization()
    if args.attempt == 3 or args.v3_contract is not None or args.v3_plan is not None:
        if args.attempt != 3 or args.phase != "A2_q":
            raise ValueError("V3 diagnostic entry is fixed to A2_q attempt 3")
        if args.v3_contract is None or args.v3_plan is None:
            raise ValueError("A2_q attempt 3 requires both frozen V3 contract files")
        if _V3_CONTRACT_SHA256 is None or _V3_PLAN_SHA256 is None:
            raise RuntimeError(
                "Task43 V3 contract bytes are not yet frozen in the adapter"
            )
        contract_path = _bind_file(
            _V3_CONTRACT_REL, _V3_CONTRACT_SHA256, label="V3 contract"
        )
        plan_path = _bind_file(_V3_PLAN_REL, _V3_PLAN_SHA256, label="V3 plan")
        if (
            args.v3_contract.resolve() != contract_path.resolve()
            or args.v3_plan.resolve() != plan_path.resolve()
        ):
            raise ValueError("A2_q attempt 3 CLI paths differ from the frozen V3 files")
        _validate_v3_a2_entry_contract(
            _read_json(contract_path), phase=args.phase, attempt=args.attempt
        )
        v3_diagnostic = {
            "phase": args.phase,
            "attempt": args.attempt,
            "contract_path": str(contract_path),
            "contract_sha256": _V3_CONTRACT_SHA256,
            "plan_path": str(plan_path),
            "plan_sha256": _V3_PLAN_SHA256,
            "watchdog_worker_identity": _require_v3_watchdog_worker_identity(),
        }
    elif args.attempt not in (1, 2):
        raise ValueError("A2_q attempt 3 requires a frozen V3 contract")

    attempt_root = (
        _REPO_ROOT
        / (
            "benchmarks/artifacts/task43/v3_diagnostics"
            if v3_diagnostic is not None
            else "benchmarks/artifacts/task43/v2_diagnostics"
        )
        / f"{args.phase}_attempt{args.attempt}"
    )
    output_dir = _a2_attempt_run_directory(attempt_root, args.output_dir)

    diagnostic, frozen = _validate_frozen_inputs(args.phase)
    resolved_path = (
        Path(args.resolved_config).resolve()
        if args.resolved_config is not None
        else Path(diagnostic["reference_resolved_config_path"])
    )
    if resolved_path != Path(diagnostic["reference_resolved_config_path"]):
        raise ValueError("A2 is fixed to the original Y6_1 resolved configuration")
    source_sha = str(diagnostic["current_source_sha"])
    output_dir.mkdir()
    profile_preflight_path = output_dir / "resolved_native_profile_preflight.json"
    profile_preflight = {
        **frozen["resolved_profile_compatibility"],
        "schema": "task43.v2.resolved_native_profile_preflight.v1",
        "phase": args.phase,
        "attempt": args.attempt,
    }
    profile_preflight_path.write_text(
        json.dumps(profile_preflight, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    diagnostic["resolved_profile_preflight_path"] = str(profile_preflight_path)
    diagnostic["resolved_profile_preflight_sha256"] = _sha256(profile_preflight_path)
    frozen["resolved_profile_compatibility"]["preflight_record_path"] = str(
        profile_preflight_path
    )
    frozen["resolved_profile_compatibility"]["preflight_record_sha256"] = diagnostic[
        "resolved_profile_preflight_sha256"
    ]
    from src.runners.p6_condensed_direct import run_p6_condensed_direct

    try:
        result = run_p6_condensed_direct(
            frozen["resolved_payload"],
            output_dir,
            source_sha=source_sha,
            task43_v2_diagnostic=diagnostic,
            task43_v3_diagnostic=v3_diagnostic,
        )
    except BaseException:
        summary_path = output_dir / "p6_condensed_direct_summary.json"
        if summary_path.is_file():
            print(summary_path.read_text(encoding="utf-8"), file=sys.stderr)
        raise
    summary_path = output_dir / "p6_condensed_direct_summary.json"
    comparison_path = output_dir / "comparison_record.json"

    def postprocess_native_result() -> int:
        def write_postprocess_json(path: Path, record: dict[str, Any]) -> None:
            if v3_diagnostic is not None:
                from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
                    write_atomic_json,
                )

                write_atomic_json(path, record, refuse_overwrite=False)
                return
            path.write_text(
                json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )

        summary_path = Path(result["summary"])
        runner_summary = _read_json(summary_path)
        runner_summary["task43_v2_resolved_profile_compatibility"] = frozen[
            "resolved_profile_compatibility"
        ]
        if v3_diagnostic is not None:
            runner_summary["task43_v3_invocation"] = v3_diagnostic
        retry_binding = None
        if retry_authorization is not None:
            retry_binding = {
                "path": retry_authorization["path"],
                "sha256": retry_authorization["sha256"],
                "replaces_unused_A2_R_slot": True,
                "attempt_1_watchdog_summary_sha256": retry_authorization["record"][
                    "consumed_attempt_1"
                ]["watchdog_summary_sha256"],
            }
            runner_summary["task43_v2_retry_authorization"] = retry_binding
        write_postprocess_json(summary_path, runner_summary)
        comparison_callback = lambda: _comparison_record(
            args.phase,
            output_dir,
            runner_summary,
            diagnostic,
            frozen["old_summary"],
        )
        comparison = comparison_callback()
        if retry_binding is not None:
            comparison["retry_authorization"] = retry_binding
            comparison.update(
                same_group_R_factor_may_continue=False,
                A2_R_status="cancelled_by_A2_q_retry_authorization",
                endpoint_qualification_scope=(
                    "local A2_q endpoint comparison only; does not establish a complete "
                    "A2 q/R reference or unlock B/C"
                ),
            )
        if v3_diagnostic is not None:
            comparison.update(
                same_group_R_factor_may_continue=False,
                A2_R_status="not_run_locked_by_V3_scope",
                endpoint_qualification_scope=(
                    "local A2_q attempt-3 diagnostic only; no A2_R, B, or C continuation"
                ),
            )
        write_postprocess_json(comparison_path, comparison)
        comparison["comparison_record_sha256"] = _sha256(comparison_path)
        summary = _read_json(summary_path)
        summary["task43_v2_comparison"] = {
            "path": str(comparison_path),
            "sha256": comparison["comparison_record_sha256"],
            "endpoint_qualified": comparison["endpoint_qualified"],
            "primary_perturbation_gate": comparison["primary_perturbation_gate"],
            "hard_solver_gate": comparison["hard_solver_gate"],
            "extra_same_lu_uncertainty_gate": comparison["extra_same_lu_uncertainty"][
                "pass_10_percent_output_uncertainty_gate"
            ],
            "same_group_R_factor_may_continue": comparison[
                "same_group_R_factor_may_continue"
            ],
            "A2_R_status": comparison.get("A2_R_status", "not_cancelled_by_retry"),
            "endpoint_qualification_scope": comparison.get(
                "endpoint_qualification_scope",
                "frozen A2 endpoint comparison",
            ),
        }
        write_postprocess_json(summary_path, summary)
        print(
            json.dumps(
                {
                    "phase": args.phase,
                    "attempt": args.attempt,
                    "runner_passed": result["passed"],
                    "endpoint_qualified": comparison["endpoint_qualified"],
                    "hard_solver_gate": comparison["hard_solver_gate"],
                    "same_group_R_factor_may_continue": comparison[
                        "same_group_R_factor_may_continue"
                    ],
                    "summary": str(summary_path),
                    "comparison": str(comparison_path),
                    "comparison_sha256": _sha256(comparison_path),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        # V3 spends the former B slot only on A2_q attempt 3; all continuation
        # paths remain closed even if the local endpoint gates pass.
        if v3_diagnostic is not None:
            return 0 if comparison["hard_solver_gate"] else 2
        # A failed perturbation/uncertainty gate is a preserved diagnostic result;
        # only a hard solver failure blocks the predeclared same-space R factor.
        return 0 if comparison["hard_solver_gate"] else 2


    if v3_diagnostic is not None:
        return _task43_v3_postprocess_fail_closed(
            postprocess_native_result,
            summary_path=summary_path,
            run_directory=output_dir,
            phase=args.phase,
            comparison_path=comparison_path,
        )
    return postprocess_native_result()

if __name__ == "__main__":
    raise SystemExit(main())
