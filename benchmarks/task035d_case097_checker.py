from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_COMBINED_HP_ACTIVE_FE_DOFS,
    TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256,
    TASK035D_COMBINED_HP_AUTHORITY_PATH,
    TASK035D_COMBINED_HP_PLAN_FILE_SHA256,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_COMBINED_HP_PLAN_PATH,
    TASK035D_COMBINED_HP_SOLVE_ROWS,
    TASK035D_HP_FACTORIAL_BRIDGE_ACTIVE_FE_DOFS,
    TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_FILE_SHA256,
    TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_FILE_SHA256,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH,
    TASK035D_HP_FACTORIAL_BRIDGE_SOLVE_ROWS,
    TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
    TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256,
    TASK035D_LOCAL_H_AUTHORITY_PATH,
    TASK035D_LOCAL_H_PLAN_FILE_SHA256,
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_PATH,
    TASK035D_LOCAL_H_SOLVE_ROWS,
    TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS,
    TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256,
    TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH,
    TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256,
    TASK035D_SIDEWALL_GUARD_PLAN_PATH,
    TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
    TASK035D_T30_ACTIVE_FE_DOFS,
    TASK035D_T30_AUTHORITY_FILE_SHA256,
    TASK035D_T30_AUTHORITY_PATH,
    TASK035D_T30_PLAN_FILE_SHA256,
    TASK035D_T30_PLAN_PATH,
    TASK035D_T30_SOLVE_ROWS,
    task035d_case097_combined_hp_plan_authority_gate,
    task035d_case097_combined_hp_solver_gate,
    task035d_case097_hp_factorial_bridge_plan_authority_gate,
    task035d_case097_hp_factorial_bridge_solver_gate,
    task035d_case097_local_h_plan_authority_gate,
    task035d_case097_local_h_solver_gate,
    task035d_case097_plan_authority_gate,
    task035d_case097_sidewall_guard_plan_authority_gate,
    task035d_case097_sidewall_guard_solver_gate,
    task035d_case097_t30_solver_gate,
)
from benchmarks.task035d_selective_face_case097_gates import (
    TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS,
    TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256,
    TASK035D_SELECTIVE_FACE_AUTHORITY_PATH,
    TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256,
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
    TASK035D_SELECTIVE_FACE_PLAN_PATH,
    TASK035D_SELECTIVE_FACE_SOLVE_ROWS,
    task035d_case097_selective_face_plan_authority_gate,
    task035d_case097_selective_face_solver_gate,
)
from benchmarks.task035d_selective_face_dwr_checker import (
    load_selective_face_coarse_endpoint,
    task035d_selective_face_dwr_report_gate,
)
from src.adaptivity.high_order_same_error import (
    compare_cross_mesh_fields,
    compare_observables,
    compare_significant_channels_to_reference_v1,
)


ROOT = Path(__file__).resolve().parents[1]
CASE097_RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
    / "records"
)
SIGNIFICANT_REFERENCE_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "significant_channel_reference_v1.json"
)
SIGNIFICANT_REFERENCE_SHA256 = (
    "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3"
)
P5P6_CONTROL_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "global_hexa_p5_p6_h10_assembly_time_condensed_independent_mpi8.json"
)
P5P6_CONTROL_SHA256 = "9f7f44efb52b44c587ef59a57524849e08da81a6fcd5d90ec18e7b69e4f33ded"
FIELD_AUTHORITY_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "fixed_p5trace_p6interior_h15_mpi8.json"
)
FIELD_AUTHORITY_SHA256 = (
    "84c9b898100bc2f223913a144d9b7a9a324ef17d9164610c622b3ecc480d870a"
)
CASE096_AUTHORITY_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "096_hybrid_channel_memory_closure"
    / "records"
    / "p6_h10_mpi8_six_path_v1.json"
)
CASE096_AUTHORITY_SHA256 = (
    "7e7474fa5b67d65ae255c198982010acc5d6d4d5087f793eb7c2de76c5bbee0a"
)
STATIC_P6_ROWS = 51_272
STATIC_P6_MATRIX_NNZ = 41_989_040
STATIC_P6_FACTOR_NNZ = 212_343_992
STATIC_P6_PEAK_GIB = 14.721755981445312
MANDATORY_PEAK_GIB = STATIC_P6_PEAK_GIB * 0.80
PREFERRED_PEAK_GIB = STATIC_P6_PEAK_GIB * 0.60
ENERGY_CLOSURE_TOLERANCE = 1.0e-9
EXPECTED_MPI_SIZE = 8


def _candidate_spec(candidate_id: str) -> dict[str, Any]:
    if candidate_id == "t30":
        return {
            "candidate_id": "t30",
            "plan_path": TASK035D_T30_PLAN_PATH,
            "plan_file_sha256": TASK035D_T30_PLAN_FILE_SHA256,
            "authority_path": TASK035D_T30_AUTHORITY_PATH,
            "authority_file_sha256": (TASK035D_T30_AUTHORITY_FILE_SHA256),
            "active_fe_dofs": TASK035D_T30_ACTIVE_FE_DOFS,
            "solve_rows": TASK035D_T30_SOLVE_ROWS,
            "launch_schema": "task035d.case097-t30-launch-gate.v1",
            "launch_status": "task035d_t30_launch_authority_pass",
            "check_schema": "task035d.case097-t30-candidate-check.v1",
            "pass_status": "task035d_t30_p_only_candidate_pass",
            "negative_status": "task035d_t30_p_only_controlled_negative",
            "evidence_failure_status": ("task035d_t30_checker_evidence_failure"),
            "benchmark_id": "task035d_case097_t30_candidate",
            "plan_context": "frozen T30 plan",
            "authority_context": "frozen MPI8 T30 plan authority",
            "plan_gate": task035d_case097_plan_authority_gate,
            "solver_gate": task035d_case097_t30_solver_gate,
            "candidate_option_required": False,
            "h_nm": 10.0,
            "plan_option": "--stage4-variable-p-cell-degree-plan",
            "plan_sha_option": ("--stage4-variable-p-cell-degree-plan-sha256"),
            "forbidden_plan_option": "--stage4-local-h-refinement-plan",
            "classification_pass": "p_only_candidate_pass_pending_local_h",
            "pass_accuracy_credit": ("fresh_p_only_accuracy_and_resource_pass"),
            "selection_credit": None,
            "ordinary_default_check": "ordinary_default_unchanged",
        }
    if candidate_id == "sidewall_z0_guard_v1":
        return {
            "candidate_id": "sidewall_z0_guard_v1",
            "plan_path": TASK035D_SIDEWALL_GUARD_PLAN_PATH,
            "plan_file_sha256": (TASK035D_SIDEWALL_GUARD_PLAN_FILE_SHA256),
            "authority_path": TASK035D_SIDEWALL_GUARD_AUTHORITY_PATH,
            "authority_file_sha256": (TASK035D_SIDEWALL_GUARD_AUTHORITY_FILE_SHA256),
            "active_fe_dofs": (TASK035D_SIDEWALL_GUARD_ACTIVE_FE_DOFS),
            "solve_rows": TASK035D_SIDEWALL_GUARD_SOLVE_ROWS,
            "launch_schema": ("task035d.case097-sidewall-z0-guard-launch-gate.v1"),
            "launch_status": ("task035d_sidewall_z0_guard_launch_authority_pass"),
            "check_schema": ("task035d.case097-sidewall-z0-guard-candidate-check.v1"),
            "pass_status": ("task035d_sidewall_z0_guard_p_only_candidate_pass"),
            "negative_status": (
                "task035d_sidewall_z0_guard_p_only_controlled_negative"
            ),
            "evidence_failure_status": (
                "task035d_sidewall_z0_guard_checker_evidence_failure"
            ),
            "benchmark_id": ("task035d_case097_sidewall_z0_guard_candidate"),
            "plan_context": "frozen sidewall-z0 guard plan",
            "authority_context": ("frozen MPI8 sidewall-z0 guard plan authority"),
            "plan_gate": (task035d_case097_sidewall_guard_plan_authority_gate),
            "solver_gate": task035d_case097_sidewall_guard_solver_gate,
            "candidate_option_required": True,
            "h_nm": 10.0,
            "plan_option": "--stage4-variable-p-cell-degree-plan",
            "plan_sha_option": ("--stage4-variable-p-cell-degree-plan-sha256"),
            "forbidden_plan_option": "--stage4-local-h-refinement-plan",
            "classification_pass": "p_only_candidate_pass_pending_local_h",
            "pass_accuracy_credit": ("fresh_p_only_accuracy_and_resource_pass"),
            "selection_credit": None,
            "ordinary_default_check": "ordinary_default_unchanged",
        }
    if candidate_id == TASK035D_LOCAL_H_PLAN_NAME:
        return {
            "candidate_id": TASK035D_LOCAL_H_PLAN_NAME,
            "plan_path": TASK035D_LOCAL_H_PLAN_PATH,
            "plan_file_sha256": TASK035D_LOCAL_H_PLAN_FILE_SHA256,
            "authority_path": TASK035D_LOCAL_H_AUTHORITY_PATH,
            "authority_file_sha256": (TASK035D_LOCAL_H_AUTHORITY_FILE_SHA256),
            "active_fe_dofs": TASK035D_LOCAL_H_ACTIVE_FE_DOFS,
            "solve_rows": TASK035D_LOCAL_H_SOLVE_ROWS,
            "launch_schema": ("task035d.case097-h15-local-h-launch-gate.v1"),
            "launch_status": ("task035d_h15_local_h_launch_authority_pass"),
            "check_schema": ("task035d.case097-h15-local-h-candidate-check.v1"),
            "pass_status": "task035d_h15_local_h_candidate_pass",
            "negative_status": ("task035d_h15_local_h_controlled_negative"),
            "evidence_failure_status": (
                "task035d_h15_local_h_checker_evidence_failure"
            ),
            "benchmark_id": ("task035d_case097_h15_top_air_local_h_candidate"),
            "plan_context": "frozen h15 top-air local-h plan",
            "authority_context": ("frozen MPI1/2/8 h15 local-h production authority"),
            "plan_gate": task035d_case097_local_h_plan_authority_gate,
            "solver_gate": task035d_case097_local_h_solver_gate,
            "candidate_option_required": True,
            "h_nm": 15.0,
            "plan_option": "--stage4-local-h-refinement-plan",
            "plan_sha_option": ("--stage4-local-h-refinement-plan-sha256"),
            "forbidden_plan_option": ("--stage4-variable-p-cell-degree-plan"),
            "classification_pass": (
                "local_h_structural_resource_anchor_pass_without_dwr_credit"
            ),
            "pass_accuracy_credit": (
                "fresh_local_h_accuracy_and_resource_pass_no_dwr_selection_credit"
            ),
            "selection_credit": {
                "structural_resource_anchor": True,
                "actual_channel_dwr": False,
                "goal_oriented_selection_credit": False,
            },
            "ordinary_default_check": "ordinary_default_unchanged",
        }
    if candidate_id == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME:
        return {
            "candidate_id": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            "plan_path": TASK035D_HP_FACTORIAL_BRIDGE_PLAN_PATH,
            "plan_file_sha256": (TASK035D_HP_FACTORIAL_BRIDGE_PLAN_FILE_SHA256),
            "authority_path": TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_PATH,
            "authority_file_sha256": (
                TASK035D_HP_FACTORIAL_BRIDGE_AUTHORITY_FILE_SHA256
            ),
            "active_fe_dofs": TASK035D_HP_FACTORIAL_BRIDGE_ACTIVE_FE_DOFS,
            "solve_rows": TASK035D_HP_FACTORIAL_BRIDGE_SOLVE_ROWS,
            "launch_schema": ("task035d.case097-hp-factorial-bridge-launch-gate.v1"),
            "launch_status": ("task035d_hp_factorial_bridge_launch_authority_pass"),
            "check_schema": ("task035d.case097-hp-factorial-bridge-candidate-check.v1"),
            "pass_status": ("task035d_hp_factorial_bridge_candidate_pass"),
            "negative_status": ("task035d_hp_factorial_bridge_controlled_negative"),
            "evidence_failure_status": (
                "task035d_hp_factorial_bridge_checker_evidence_failure"
            ),
            "benchmark_id": ("task035d_case097_hp_factorial_bridge_candidate"),
            "plan_context": (
                "frozen h15 one-sided top-air plus remote-p5-interior factorial bridge"
            ),
            "authority_context": ("frozen MPI1/2/8 hp-factorial-bridge authority"),
            "plan_gate": (task035d_case097_hp_factorial_bridge_plan_authority_gate),
            "solver_gate": (task035d_case097_hp_factorial_bridge_solver_gate),
            "candidate_option_required": True,
            "h_nm": 15.0,
            "plan_option": "--stage4-local-h-refinement-plan",
            "plan_sha_option": ("--stage4-local-h-refinement-plan-sha256"),
            "forbidden_plan_option": ("--stage4-variable-p-cell-degree-plan"),
            "classification_pass": (
                "hp_factorial_bridge_candidate_pass_without_dwr_or_"
                "variable_trace_credit"
            ),
            "pass_accuracy_credit": (
                "fresh_factorial_bridge_accuracy_and_resource_pass_"
                "no_dwr_or_variable_trace_credit"
            ),
            "selection_credit": {
                "structural_resource_anchor": True,
                "factorial_bridge_credit": True,
                "actual_channel_dwr": False,
                "goal_oriented_selection_credit": False,
                "complete_combined_hp_credit": False,
            },
            "ordinary_default_check": ("ordinary_default_and_lifecycle"),
        }
    if candidate_id == TASK035D_COMBINED_HP_PLAN_NAME:
        return {
            "candidate_id": TASK035D_COMBINED_HP_PLAN_NAME,
            "plan_path": TASK035D_COMBINED_HP_PLAN_PATH,
            "plan_file_sha256": TASK035D_COMBINED_HP_PLAN_FILE_SHA256,
            "authority_path": TASK035D_COMBINED_HP_AUTHORITY_PATH,
            "authority_file_sha256": (TASK035D_COMBINED_HP_AUTHORITY_FILE_SHA256),
            "active_fe_dofs": TASK035D_COMBINED_HP_ACTIVE_FE_DOFS,
            "solve_rows": TASK035D_COMBINED_HP_SOLVE_ROWS,
            "launch_schema": ("task035d.case097-combined-hp-interior-launch-gate.v1"),
            "launch_status": ("task035d_combined_hp_interior_launch_authority_pass"),
            "check_schema": (
                "task035d.case097-combined-hp-interior-candidate-check.v1"
            ),
            "pass_status": ("task035d_combined_hp_interior_candidate_pass"),
            "negative_status": ("task035d_combined_hp_interior_controlled_negative"),
            "evidence_failure_status": (
                "task035d_combined_hp_interior_checker_evidence_failure"
            ),
            "benchmark_id": ("task035d_case097_combined_hp_interior_candidate"),
            "plan_context": ("frozen h15 symmetric top-air variable-interior plan"),
            "authority_context": ("frozen MPI1/2/8 combined hp-interior authority"),
            "plan_gate": (task035d_case097_combined_hp_plan_authority_gate),
            "solver_gate": task035d_case097_combined_hp_solver_gate,
            "candidate_option_required": True,
            "h_nm": 15.0,
            "plan_option": "--stage4-local-h-refinement-plan",
            "plan_sha_option": ("--stage4-local-h-refinement-plan-sha256"),
            "forbidden_plan_option": ("--stage4-variable-p-cell-degree-plan"),
            "classification_pass": (
                "combined_local_h_variable_interior_p_candidate_pass_"
                "without_dwr_or_variable_trace_credit"
            ),
            "pass_accuracy_credit": (
                "fresh_combined_hp_interior_accuracy_and_resource_pass_"
                "no_dwr_or_variable_trace_credit"
            ),
            "selection_credit": {
                "structural_resource_anchor": True,
                "actual_channel_dwr": False,
                "goal_oriented_selection_credit": False,
                "complete_combined_hp_credit": False,
            },
            "ordinary_default_check": ("ordinary_default_and_lifecycle"),
            "requires_actual_channel_dwr": False,
        }
    if candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME:
        return {
            "candidate_id": TASK035D_SELECTIVE_FACE_PLAN_NAME,
            "plan_path": TASK035D_SELECTIVE_FACE_PLAN_PATH,
            "plan_file_sha256": (TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
            "authority_path": TASK035D_SELECTIVE_FACE_AUTHORITY_PATH,
            "authority_file_sha256": (TASK035D_SELECTIVE_FACE_AUTHORITY_FILE_SHA256),
            "active_fe_dofs": (TASK035D_SELECTIVE_FACE_ACTIVE_FE_DOFS),
            "solve_rows": TASK035D_SELECTIVE_FACE_SOLVE_ROWS,
            "launch_schema": ("task035d.case097-selective-p6-face-launch-gate.v1"),
            "launch_status": ("task035d_selective_p6_face_launch_authority_pass"),
            "check_schema": ("task035d.case097-selective-p6-face-candidate-check.v1"),
            "pass_status": ("task035d_selective_p6_face_candidate_pass"),
            "negative_status": ("task035d_selective_p6_face_controlled_negative"),
            "evidence_failure_status": (
                "task035d_selective_p6_face_checker_evidence_failure"
            ),
            "benchmark_id": ("task035d_case097_selective_p6_face_candidate"),
            "plan_context": (
                "frozen h15 one-sided local-h plus ten selective p6 faces"
            ),
            "authority_context": ("frozen MPI1/2/8 selective-p6-face authority"),
            "plan_gate": (task035d_case097_selective_face_plan_authority_gate),
            "solver_gate": task035d_case097_selective_face_solver_gate,
            "candidate_option_required": True,
            "h_nm": 15.0,
            "plan_option": "--stage4-local-h-refinement-plan",
            "plan_sha_option": ("--stage4-local-h-refinement-plan-sha256"),
            "forbidden_plan_option": ("--stage4-variable-p-cell-degree-plan"),
            "classification_pass": (
                "selective_face_candidate_pass_with_posthoc_dwr_attribution"
            ),
            "pass_accuracy_credit": (
                "fresh_selective_face_accuracy_resource_and_actual_36_goal_"
                "posthoc_dwr_attribution_pass"
            ),
            "selection_credit": {
                "structural_resource_anchor": True,
                "actual_channel_dwr": False,
                "goal_oriented_selection_credit": False,
                "posthoc_actual_action_attribution": False,
                "complete_combined_hp_credit": False,
            },
            "ordinary_default_check": ("ordinary_default_and_lifecycle"),
            "requires_actual_channel_dwr": True,
        }
    raise Task035dEvidenceError(f"unsupported Task035d candidate id: {candidate_id}")


class Task035dEvidenceError(ValueError):
    """Raised when hash-bound Task035d evidence is incomplete or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task035dEvidenceError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_sha(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{context} must be an object")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{context} must be an array",
    )
    return value


def _finite(value: Any, context: str) -> float:
    _require(
        isinstance(value, (int, float)) and math.isfinite(float(value)),
        f"{context} must be finite",
    )
    return float(value)


def _load_json(
    path: Path,
    *,
    expected_sha256: str | None,
    context: str,
) -> tuple[dict[str, Any], str]:
    path = path.resolve()
    _require(path.is_file(), f"{context} is missing: {path}")
    observed_sha256 = _sha256(path)
    if expected_sha256 is not None:
        _require(
            _valid_sha(expected_sha256, 64),
            f"{context} expected SHA-256 is invalid",
        )
        _require(
            observed_sha256 == expected_sha256.lower(),
            (
                f"{context} SHA-256 mismatch: expected {expected_sha256}, "
                f"got {observed_sha256}"
            ),
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Task035dEvidenceError(f"{context} is not valid JSON: {error}") from error
    return dict(_mapping(value, context)), observed_sha256


def _resolve_path(value: Any, *, context: str) -> Path:
    _require(
        isinstance(value, str) and bool(value),
        f"{context} must be a non-empty path",
    )
    candidate = Path(value)
    path = candidate if candidate.is_absolute() else ROOT / candidate
    path = path.resolve()
    _require(path.is_file(), f"{context} is missing: {path}")
    return path


def _path_from_root(path: Path) -> str:
    path = path.resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _same_number(
    left: Any,
    right: Any,
    *,
    context: str,
    tolerance: float = 1.0e-9,
) -> None:
    left_value = _finite(left, f"{context}.left")
    right_value = _finite(right, f"{context}.right")
    _require(
        math.isclose(
            left_value,
            right_value,
            rel_tol=0.0,
            abs_tol=tolerance,
        ),
        f"{context} mismatch: {left_value} != {right_value}",
    )


def _load_frozen_authorities() -> dict[str, Any]:
    significant, significant_sha = _load_json(
        SIGNIFICANT_REFERENCE_PATH,
        expected_sha256=SIGNIFICANT_REFERENCE_SHA256,
        context="significant channel reference v1",
    )
    _require(
        significant.get("schema_version") == "task035b.significant-channel-reference.v1"
        and significant.get("status") == "significant_channel_reference_v1_frozen"
        and significant.get("pass") is True
        and significant.get("mechanical_validation_pass") is True,
        "significant channel reference v1 is not frozen and qualified",
    )

    p5p6, p5p6_sha = _load_json(
        P5P6_CONTROL_PATH,
        expected_sha256=P5P6_CONTROL_SHA256,
        context="global p5/p6 h10 control",
    )
    _require(
        p5p6.get("schema_version") == "task035.actual-global-r5-watchdog.v1"
        and p5p6.get("status") == "actual_global_r5_pass"
        and (p5p6.get("qualification") or {}).get("pass") is True,
        "global p5/p6 h10 control is not qualified",
    )
    coarse = _mapping(p5p6.get("coarse"), "p5/p6 control coarse")
    enriched = _mapping(p5p6.get("enriched"), "p5/p6 control enriched")
    for role, row, degree in (
        ("coarse", coarse, 5),
        ("enriched", enriched, 6),
    ):
        _require(
            row.get("degree") == degree
            and row.get("h_nm") == 10.0
            and row.get("mpi_size") == EXPECTED_MPI_SIZE
            and row.get("official_result") is True
            and row.get("case_status") == "completed",
            f"global p5/p6 {role} identity is invalid",
        )

    field, field_sha = _load_json(
        FIELD_AUTHORITY_PATH,
        expected_sha256=FIELD_AUTHORITY_SHA256,
        context="frozen field-probe authority",
    )
    field_gate = _mapping(
        field.get("selected_field_interface_error_gate"),
        "frozen field-probe authority gate",
    )
    _require(
        field_gate.get("schema_version") == "task035b.cross-mesh-field-comparison.v1"
        and field_gate.get("status") == "measured_frozen_physical_gauss_probes"
        and field_gate.get("no_probe_dropping") is True
        and field_gate.get("no_threshold_relaxation") is True,
        "frozen field-probe authority is invalid",
    )

    case096, case096_sha = _load_json(
        CASE096_AUTHORITY_PATH,
        expected_sha256=CASE096_AUTHORITY_SHA256,
        context="Case096 six-path authority",
    )
    _require(
        case096.get("schema_version") == "task035c.case096-p6-six-path.v1"
        and case096.get("pass") is True,
        "Case096 six-path authority is not qualified",
    )
    full_static = _mapping(
        (case096.get("models") or {}).get("full_static"),
        "Case096 Full3D static model",
    )
    _require(
        full_static.get("kind") == "full3d"
        and full_static.get("degree") == 6
        and full_static.get("h_nm") == 10.0
        and full_static.get("mpi_size") == EXPECTED_MPI_SIZE
        and full_static.get("formal_pass") is True
        and full_static.get("active_rows") == STATIC_P6_ROWS
        and full_static.get("matrix_nnz") == STATIC_P6_MATRIX_NNZ
        and full_static.get("factor_nnz") == STATIC_P6_FACTOR_NNZ
        and full_static.get("peak_memory_gib") == STATIC_P6_PEAK_GIB,
        "Case096 Full3D static resource baseline drifted",
    )
    return {
        "significant": significant,
        "p5p6": p5p6,
        "field": field,
        "case096": case096,
        "full_static": full_static,
        "authorities": {
            "significant_channel_reference_v1": {
                "path": _path_from_root(SIGNIFICANT_REFERENCE_PATH),
                "sha256": significant_sha,
            },
            "global_p5p6_h10": {
                "path": _path_from_root(P5P6_CONTROL_PATH),
                "sha256": p5p6_sha,
            },
            "field_probe_authority": {
                "path": _path_from_root(FIELD_AUTHORITY_PATH),
                "sha256": field_sha,
            },
            "case096_six_path": {
                "path": _path_from_root(CASE096_AUTHORITY_PATH),
                "sha256": case096_sha,
            },
        },
    }


def _control_field_directories(
    authorities: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    p5p6 = _mapping(authorities.get("p5p6"), "p5/p6 authority")
    raw = _mapping(p5p6.get("raw_evidence"), "p5/p6 raw evidence")
    run_value = raw.get("run_directory")
    _require(isinstance(run_value, str), "p5/p6 run directory is missing")
    run_dir = Path(run_value)
    run_dir = run_dir if run_dir.is_absolute() else ROOT / run_dir
    run_dir = run_dir.resolve()
    p5_dir = run_dir / "coarse_p5"
    p6_dir = run_dir / "enriched_p6"

    field_record = _mapping(authorities.get("field"), "field authority")
    gate = _mapping(
        field_record.get("selected_field_interface_error_gate"),
        "field authority gate",
    )
    selections = _mapping(gate.get("selections"), "field selections")
    expected_by_role: dict[str, list[Mapping[str, Any]]] = {}
    for selection_name in ("volume", "interface"):
        selection = _mapping(
            selections.get(selection_name),
            f"field selection {selection_name}",
        )
        sampling = _mapping(
            selection.get("sampling_authorities"),
            f"field sampling authorities {selection_name}",
        )
        for role in ("global_p5_control", "global_p6_reference"):
            role_row = _mapping(
                sampling.get(role),
                f"{selection_name} {role} authority",
            )
            shards = [
                _mapping(item, f"{selection_name} {role} shard")
                for item in _sequence(
                    role_row.get("shards"),
                    f"{selection_name} {role} shards",
                )
            ]
            _require(
                len(shards) == EXPECTED_MPI_SIZE,
                f"{selection_name} {role} must contain eight shards",
            )
            if role in expected_by_role:
                _require(
                    [item.get("sha256") for item in shards]
                    == [item.get("sha256") for item in expected_by_role[role]],
                    f"{role} shard hashes differ between field selections",
                )
            else:
                expected_by_role[role] = shards

    observed: dict[str, Any] = {}
    for role, directory in (
        ("global_p5_control", p5_dir),
        ("global_p6_reference", p6_dir),
    ):
        rows = []
        for rank, authority in enumerate(expected_by_role[role]):
            path = directory / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
            _require(path.is_file(), f"{role} field shard is missing: {path}")
            expected = authority.get("sha256")
            _require(
                _valid_sha(expected, 64),
                f"{role} field shard {rank} has an invalid authority hash",
            )
            actual = _sha256(path)
            _require(
                actual == expected,
                f"{role} field shard {rank} SHA-256 mismatch",
            )
            rows.append(
                {
                    "rank": rank,
                    "path": _path_from_root(path),
                    "sha256": actual,
                }
            )
        observed[role] = rows
    return p5_dir, p6_dir, observed


def _source_identity(record: Mapping[str, Any]) -> str:
    source = _mapping(record.get("source"), "candidate source")
    values = {
        str(source[name])
        for name in (
            "commit_sha",
            "verified_clean_sha",
            "head_after_sha",
        )
        if isinstance(source.get(name), str)
    }
    _require(len(values) == 1, "candidate source SHA fields disagree")
    source_sha = next(iter(values))
    _require(_valid_sha(source_sha, 40), "candidate source SHA is invalid")
    _require(
        source.get("tracked_source_dirty") is False
        and source.get("stable_and_clean_after") is True
        and source.get("status_after") == "",
        "candidate source is not clean and stable",
    )
    return source_sha


def _git_tracked(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _checker_source_provenance() -> dict[str, Any]:
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise Task035dEvidenceError(
            f"checker source identity is unreadable: {error}"
        ) from error
    _require(_valid_sha(head, 40), "checker source SHA is invalid")
    _require(
        status == "",
        "checker requires a clean source tree before evidence evaluation",
    )
    return {
        "commit_sha": head,
        "source_clean_verified": True,
        "status": status,
    }


def _command_option(command: Sequence[str], option: str) -> str:
    indices = [index for index, value in enumerate(command) if value == option]
    _require(
        len(indices) == 1 and indices[0] + 1 < len(command),
        f"candidate command must contain exactly one {option}",
    )
    return command[indices[0] + 1]


def _optional_command_option(
    command: Sequence[str],
    option: str,
) -> str | None:
    indices = [index for index, value in enumerate(command) if value == option]
    _require(
        len(indices) <= 1 and (not indices or indices[0] + 1 < len(command)),
        f"candidate command contains an invalid {option}",
    )
    return command[indices[0] + 1] if indices else None


def _candidate_launch_contract(
    record: Mapping[str, Any],
    *,
    source_sha: str,
    candidate_id: str = "t30",
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    command = [
        str(value) for value in _sequence(record.get("command"), "candidate command")
    ]
    plan_path = Path(
        _command_option(
            command,
            spec["plan_option"],
        )
    ).resolve()
    authority_path = Path(
        _command_option(command, "--task035d-plan-authority")
    ).resolve()
    embedded = _mapping(
        record.get("task035d_case097_launch_gate"),
        "candidate embedded Task035d launch gate",
    )
    embedded_checks = _mapping(
        embedded.get("checks"),
        "candidate embedded launch checks",
    )
    resource_policy = _mapping(
        record.get("resource_policy"),
        "candidate resource policy",
    )
    command_candidate = _optional_command_option(
        command,
        "--task035d-candidate-id",
    )
    record_candidate = record.get("task035d_candidate_id")
    requires_actual_channel_dwr = bool(spec.get("requires_actual_channel_dwr"))
    selective_phase = _optional_command_option(
        command,
        "--task035d-selective-face-dwr-phase",
    )
    nested_phase = _optional_command_option(
        command,
        "--task035d-nested-p-dwr-phase",
    )
    selective_authority_path = _optional_command_option(
        command,
        "--task035d-significant-channel-authority",
    )
    selective_authority_sha = _optional_command_option(
        command,
        "--task035d-significant-channel-authority-sha256",
    )
    coarse_manifest_value = _optional_command_option(
        command,
        "--task035d-selective-face-coarse-manifest",
    )
    coarse_manifest_sha = _optional_command_option(
        command,
        "--task035d-selective-face-coarse-manifest-sha256",
    )
    selective_launch = record.get("task035d_selective_face_launch_gate")
    selective_launch = selective_launch if isinstance(selective_launch, Mapping) else {}
    selective_launch_checks = selective_launch.get("checks")
    selective_launch_checks = (
        selective_launch_checks if isinstance(selective_launch_checks, Mapping) else {}
    )
    selective_significant = selective_launch.get("significant_channel_authority")
    selective_significant = (
        selective_significant if isinstance(selective_significant, Mapping) else {}
    )
    selective_coarse = selective_launch.get("coarse_snapshot")
    selective_coarse = selective_coarse if isinstance(selective_coarse, Mapping) else {}
    selective_dwr_command_pass = True
    process_bound_parent_contract_pass = True
    command_run_dir = _optional_command_option(command, "--run-dir")
    manifest_path: Path | None = None
    if requires_actual_channel_dwr:
        if isinstance(coarse_manifest_value, str):
            raw_manifest_path = Path(coarse_manifest_value)
            manifest_path = (
                raw_manifest_path
                if raw_manifest_path.is_absolute()
                else ROOT / raw_manifest_path
            ).resolve()
        significant_authority_path = None
        if isinstance(selective_authority_path, str):
            raw_authority_path = Path(selective_authority_path)
            significant_authority_path = (
                raw_authority_path
                if raw_authority_path.is_absolute()
                else ROOT / raw_authority_path
            ).resolve()
        selective_dwr_command_pass = bool(
            selective_phase == "enriched-evaluate"
            and nested_phase is None
            and significant_authority_path == SIGNIFICANT_REFERENCE_PATH.resolve()
            and selective_authority_sha == SIGNIFICANT_REFERENCE_SHA256
            and manifest_path is not None
            and manifest_path.is_file()
            and _valid_sha(coarse_manifest_sha, 64)
            and _sha256(manifest_path) == coarse_manifest_sha
        )
        descriptor_option = _optional_command_option(
            command,
            "--parent-launch-descriptor",
        )
        descriptor_sha_option = _optional_command_option(
            command,
            "--parent-launch-descriptor-sha256",
        )
        run_dir_option = command_run_dir
        parent_descriptor = record.get("parent_launch_descriptor")
        parent_descriptor = (
            parent_descriptor if isinstance(parent_descriptor, Mapping) else {}
        )
        parent_payload = parent_descriptor.get("payload")
        parent_payload = parent_payload if isinstance(parent_payload, Mapping) else {}
        parent_process = parent_payload.get("parent_process")
        parent_process = parent_process if isinstance(parent_process, Mapping) else {}
        worker_contract = parent_payload.get("worker_contract")
        worker_contract = (
            worker_contract if isinstance(worker_contract, Mapping) else {}
        )
        descriptor_path: Path | None = None
        recorded_descriptor_path: Path | None = None
        descriptor_payload: Mapping[str, Any] = {}
        if isinstance(descriptor_option, str):
            descriptor_path = Path(descriptor_option).resolve()
        if isinstance(parent_descriptor.get("path"), str):
            recorded_descriptor_path = _resolve_path(
                parent_descriptor["path"],
                context="watchdog parent-launch descriptor",
            )
        if descriptor_path is not None and descriptor_path.is_file():
            try:
                loaded_descriptor = json.loads(
                    descriptor_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                loaded_descriptor = {}
            if isinstance(loaded_descriptor, Mapping):
                descriptor_payload = loaded_descriptor
        expected_worker_contract = {
            "degree": int(_command_option(command, "--degree")),
            "h_nm": float(_command_option(command, "--h-nm")),
            "polarization_kind": _command_option(
                command,
                "--polarization-kind",
            ),
            "run_kind": _command_option(command, "--run-kind"),
            "mpi_size": int(_command_option(command, "--mpi-size")),
            "profile": _command_option(command, "--profile"),
            "run_dir": (
                str(Path(run_dir_option).resolve())
                if isinstance(run_dir_option, str)
                else None
            ),
            "stage4_full3d_assembly_backend": _command_option(
                command,
                "--stage4-full3d-assembly-backend",
            ),
            "task035d_case097_gate": ("--task035d-case097-gate" in command),
            "task035d_candidate_id": str(command_candidate),
            "task035d_nested_p_dwr_phase": nested_phase,
            "task035d_selective_face_dwr_phase": selective_phase,
            "task035d_plan_authority_sha256": _command_option(
                command,
                "--task035d-plan-authority-sha256",
            ),
            "task035d_significant_channel_authority_sha256": (selective_authority_sha),
            "task035d_coarse_snapshot_manifest_sha256": (
                _optional_command_option(
                    command,
                    "--task035d-coarse-snapshot-manifest-sha256",
                )
            ),
            "task035d_selective_face_coarse_manifest_sha256": (coarse_manifest_sha),
            "verified_clean_sha": _command_option(
                command,
                "--verified-clean-sha",
            ),
        }
        process_bound_parent_contract_pass = bool(
            descriptor_path is not None
            and isinstance(run_dir_option, str)
            and descriptor_path.parent == Path(run_dir_option).resolve()
            and descriptor_path.name == "parent_launch_descriptor.json"
            and _valid_sha(descriptor_sha_option, 64)
            and _sha256(descriptor_path) == descriptor_sha_option
            and recorded_descriptor_path == descriptor_path
            and parent_descriptor.get("sha256") == descriptor_sha_option
            and parent_descriptor.get("secret_token_persisted") is False
            and descriptor_payload == parent_payload
            and parent_payload.get("schema_version")
            == "task033.watchdog-parent-launch.v1"
            and _valid_sha(parent_payload.get("token_sha256"), 64)
            and set(parent_process)
            == {
                "pid",
                "parent_pid",
                "start_time_ticks",
                "role",
            }
            and parent_process.get("role") == "resource_watchdog_parent"
            and isinstance(parent_process.get("pid"), int)
            and parent_process.get("pid") > 0
            and isinstance(parent_process.get("parent_pid"), int)
            and parent_process.get("parent_pid") >= 0
            and isinstance(parent_process.get("start_time_ticks"), int)
            and parent_process.get("start_time_ticks") > 0
            and worker_contract == expected_worker_contract
        )
    checks = {
        "mpiexec_mpi8_worker": (
            len(command) >= 6
            and command[:3] == ["mpiexec", "-n", "8"]
            and command[3] == str(ROOT / ".venv" / "bin" / "python")
            and command[4:6] == ["-m", "benchmarks.run_task033_full3d_watchdog"]
            and "--worker" in command
        ),
        "command_scope": (
            _command_option(command, "--degree") == "6"
            and _command_option(command, "--h-nm") == str(spec["h_nm"])
            and _command_option(command, "--polarization-kind") == "s"
            and _command_option(command, "--run-kind") == "full-solve"
            and _command_option(command, "--mpi-size") == "8"
            and _command_option(command, "--profile") == "default"
            and _command_option(
                command,
                "--stage4-full3d-assembly-backend",
            )
            == TASK035D_CASE097_BACKEND
            and "--task035d-case097-gate" in command
            and "--task035c-p6-h10-gate" not in command
            and "--allow-swap" not in command
            and spec["forbidden_plan_option"] not in command
            and (
                command_candidate == candidate_id
                if spec["candidate_option_required"]
                else command_candidate in {None, candidate_id}
            )
            and (
                record_candidate == candidate_id
                if spec["candidate_option_required"]
                else record_candidate in {None, candidate_id}
            )
        ),
        "command_plan_identity": (
            plan_path == (ROOT / spec["plan_path"]).resolve()
            and _command_option(
                command,
                spec["plan_sha_option"],
            )
            == spec["plan_file_sha256"]
        ),
        "command_authority_identity": (
            authority_path == (ROOT / spec["authority_path"]).resolve()
            and _command_option(
                command,
                "--task035d-plan-authority-sha256",
            )
            == spec["authority_file_sha256"]
        ),
        "command_clean_source_identity": (
            _command_option(command, "--verified-clean-sha") == source_sha
        ),
        "embedded_launch_gate_pass": (
            embedded.get("schema_version") == spec["launch_schema"]
            and embedded.get("status") == spec["launch_status"]
            and embedded.get("pass") is True
            and embedded.get("failures") == []
            and embedded.get("accuracy_credit")
            == "none_until_fresh_12_channel_checker_passes"
            and bool(embedded_checks)
            and all(value is True for value in embedded_checks.values())
        ),
        "embedded_plan_identity": (
            (embedded.get("plan_identity") or {}).get("path") == spec["plan_path"]
            and (embedded.get("plan_identity") or {}).get("file_sha256")
            == spec["plan_file_sha256"]
            and (embedded.get("plan_identity") or {}).get(
                "actual_conforming_active_fe_dofs"
            )
            == spec["active_fe_dofs"]
            and (embedded.get("plan_identity") or {}).get("predicted_direct_solve_rows")
            == spec["solve_rows"]
        ),
        "embedded_selection_credit": (
            spec["selection_credit"] is None
            or embedded.get("selection_credit") == spec["selection_credit"]
        ),
        "actual_channel_dwr_command_scope": (selective_dwr_command_pass),
        "process_bound_parent_watchdog_contract": (process_bound_parent_contract_pass),
        "actual_channel_dwr_launch_inputs": (
            not requires_actual_channel_dwr
            or (
                selective_launch.get("schema_version")
                == ("task035d.selective-face-cross-trace-launch-gate.v1")
                and selective_launch.get("phase") == "enriched-evaluate"
                and selective_launch.get("pass") is True
                and selective_launch.get("failures") == []
                and bool(selective_launch_checks)
                and all(value is True for value in selective_launch_checks.values())
                and selective_launch.get("same_trace_only") is False
                and selective_launch.get("cross_trace_primal_prolongation") is True
                and selective_significant.get("path")
                == _path_from_root(SIGNIFICANT_REFERENCE_PATH)
                and selective_significant.get("sha256") == SIGNIFICANT_REFERENCE_SHA256
                and (selective_coarse.get("artifact_gate") or {}).get("pass") is True
                and manifest_path is not None
                and selective_coarse.get("path") == _path_from_root(manifest_path)
                and selective_coarse.get("sha256") == coarse_manifest_sha
            )
        ),
        "watchdog_no_swap_contract": (
            resource_policy.get("swap_allowed") is False
            and record.get("no_swap") is True
        ),
        "watchdog_accuracy_credit_pending_checker": (
            record.get("task035d_accuracy_credit")
            == "pending_independent_12_channel_and_field_checker"
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    _require(
        not failures,
        f"candidate launch contract failed: {failures}",
    )
    return {
        "schema_version": "task035d.case097-candidate-launch-contract.v1",
        "candidate_id": candidate_id,
        "checks": checks,
        "pass": True,
        "command": command,
        "run_dir": (
            str(Path(command_run_dir).resolve())
            if isinstance(command_run_dir, str)
            else None
        ),
        "embedded_launch_gate": dict(embedded),
        "selective_face_coarse_manifest": (
            {
                "path": str(manifest_path),
                "sha256": coarse_manifest_sha,
            }
            if requires_actual_channel_dwr and manifest_path is not None
            else None
        ),
    }


def _artifact(
    raw: Mapping[str, Any],
    key: str,
    expected_sha256: Any,
    *,
    run_dir: Path,
) -> tuple[Path, str]:
    path = _resolve_path(raw.get(key), context=f"candidate raw {key}")
    _require(
        path.parent == run_dir,
        f"candidate raw {key} is outside the candidate run directory",
    )
    _require(
        _valid_sha(expected_sha256, 64),
        f"candidate raw {key} expected SHA-256 is invalid",
    )
    observed = _sha256(path)
    _require(
        observed == expected_sha256,
        f"candidate raw {key} SHA-256 mismatch",
    )
    return path, observed


def _bound_candidate_run_directory(
    raw: Mapping[str, Any],
    launch_contract: Mapping[str, Any],
) -> Path:
    run_value = raw.get("run_directory")
    _require(
        isinstance(run_value, str) and bool(run_value),
        "candidate run directory is missing",
    )
    run_dir = Path(run_value)
    run_dir = run_dir if run_dir.is_absolute() else ROOT / run_dir
    run_dir = run_dir.resolve()
    _require(run_dir.is_dir(), f"candidate run directory is missing: {run_dir}")
    launch_run_dir = launch_contract.get("run_dir")
    _require(
        launch_run_dir is None or Path(str(launch_run_dir)).resolve() == run_dir,
        "candidate command/descriptor and raw evidence run directories differ",
    )
    return run_dir


def _load_candidate_raw(
    watchdog_path: Path,
    watchdog_sha256: str,
    *,
    candidate_id: str = "t30",
) -> dict[str, Any]:
    record, observed_watchdog_sha = _load_json(
        watchdog_path,
        expected_sha256=watchdog_sha256,
        context="Task035d candidate watchdog",
    )
    _require(
        record.get("schema_version") == "task033.full3d-watchdog.v1",
        "candidate watchdog schema is invalid",
    )
    _require(
        record.get("degree") == 6
        and record.get("h_nm") == _candidate_spec(candidate_id)["h_nm"]
        and record.get("polarization_kind") == "s"
        and record.get("run_kind") == "full-solve"
        and record.get("mpi_size") == EXPECTED_MPI_SIZE
        and record.get("profile") == "default"
        and record.get("stage4_full3d_assembly_backend_actual")
        == TASK035D_CASE097_BACKEND,
        "candidate watchdog identity is outside the frozen Case097 scope",
    )
    source_sha = _source_identity(record)
    launch_contract = _candidate_launch_contract(
        record,
        source_sha=source_sha,
        candidate_id=candidate_id,
    )
    raw = _mapping(record.get("raw_evidence"), "candidate raw evidence")
    run_dir = _bound_candidate_run_directory(raw, launch_contract)

    artifact_specs = {
        "solver_summary": record.get("solver_summary_sha256"),
        "timeline": record.get("timeline_sha256"),
        "progress": record.get("progress_sha256"),
        "stdout": record.get("stdout_sha256"),
        "dtn_orders": record.get("dtn_orders_sha256"),
    }
    artifacts: dict[str, dict[str, str]] = {}
    artifact_paths: dict[str, Path] = {}
    for key, expected in artifact_specs.items():
        path, observed = _artifact(
            raw,
            key,
            expected,
            run_dir=run_dir,
        )
        artifact_paths[key] = path
        artifacts[key] = {
            "path": _path_from_root(path),
            "sha256": observed,
        }

    solver_summary, _ = _load_json(
        artifact_paths["solver_summary"],
        expected_sha256=str(record["solver_summary_sha256"]),
        context="candidate raw solver summary",
    )
    _require(
        solver_summary == record.get("solver_summary"),
        "embedded and raw candidate solver summaries differ",
    )

    field_rows = [
        _mapping(item, "candidate field shard authority")
        for item in _sequence(
            record.get("field_shard_authority"),
            "candidate field shard authority",
        )
    ]
    raw_field_rows = [
        _mapping(item, "candidate raw field shard authority")
        for item in _sequence(
            raw.get("field_shards"),
            "candidate raw field shard authority",
        )
    ]
    _require(
        field_rows == raw_field_rows and len(field_rows) == EXPECTED_MPI_SIZE,
        "candidate field-shard authority is incomplete or inconsistent",
    )
    field_artifacts = []
    for rank, row in enumerate(field_rows):
        _require(row.get("rank") == rank, "candidate field ranks are not ordered")
        path = _resolve_path(
            row.get("path"),
            context=f"candidate field shard {rank}",
        )
        _require(
            path.parent == run_dir
            and path.name == f"fields_3d_for_paraview_rank{rank:04d}.vtu",
            f"candidate field shard {rank} path identity is invalid",
        )
        expected = row.get("sha256")
        _require(
            _valid_sha(expected, 64) and _sha256(path) == expected,
            f"candidate field shard {rank} SHA-256 mismatch",
        )
        field_artifacts.append(
            {
                "rank": rank,
                "path": _path_from_root(path),
                "sha256": expected,
            }
        )
    artifacts["field_shards"] = field_artifacts
    return {
        "record": record,
        "record_path": watchdog_path.resolve(),
        "record_sha256": observed_watchdog_sha,
        "source_sha": source_sha,
        "launch_contract": launch_contract,
        "run_dir": run_dir,
        "solver_summary": solver_summary,
        "timeline_path": artifact_paths["timeline"],
        "dtn_orders_path": artifact_paths["dtn_orders"],
        "artifacts": artifacts,
    }


def _load_selective_face_dwr_evidence(
    candidate: Mapping[str, Any],
    *,
    significant_channel_authority: Mapping[str, Any],
) -> dict[str, Any]:
    record = _mapping(
        candidate.get("record"),
        "selective-face candidate watchdog",
    )
    evidence = _mapping(
        record.get("task035d_selective_face_evidence"),
        "selective-face DWR evidence",
    )
    _require(
        evidence.get("phase") == "enriched-evaluate",
        "selective-face candidate lacks enriched DWR evidence",
    )
    path = _resolve_path(
        evidence.get("path"),
        context="selective-face DWR report",
    )
    run_dir = Path(candidate["run_dir"]).resolve()
    _require(
        path.parent == run_dir and path.name == "selective_face_dwr_report.json",
        "selective-face DWR report is outside the candidate run",
    )
    expected_sha = evidence.get("sha256")
    _require(
        _valid_sha(expected_sha, 64) and _sha256(path) == expected_sha,
        "selective-face DWR report SHA-256 mismatch",
    )
    report, observed_sha = _load_json(
        path,
        expected_sha256=str(expected_sha),
        context="selective-face DWR report",
    )
    embedded_payload = _mapping(
        evidence.get("payload"),
        "embedded selective-face DWR report",
    )
    _require(
        report == embedded_payload,
        "embedded and raw selective-face DWR reports differ",
    )
    launch_contract = _mapping(
        candidate.get("launch_contract"),
        "selective-face candidate launch contract",
    )
    coarse_descriptor = _mapping(
        launch_contract.get("selective_face_coarse_manifest"),
        "selective-face coarse manifest launch identity",
    )
    coarse_manifest_path = _resolve_path(
        coarse_descriptor.get("path"),
        context="selective-face coarse manifest",
    )
    coarse_manifest_sha = coarse_descriptor.get("sha256")
    _require(
        _valid_sha(coarse_manifest_sha, 64)
        and _sha256(coarse_manifest_path) == coarse_manifest_sha,
        "selective-face coarse manifest launch SHA-256 mismatch",
    )
    try:
        coarse_endpoint = load_selective_face_coarse_endpoint(
            coarse_manifest_path,
            expected_manifest_sha256=str(coarse_manifest_sha),
        )
    except (OSError, TypeError, ValueError) as error:
        raise Task035dEvidenceError(
            f"selective-face coarse modal endpoint failed: {error}"
        ) from error
    gate = task035d_selective_face_dwr_report_gate(
        report,
        significant_channel_authority,
        coarse_endpoint,
        expected_source_sha=str(candidate["source_sha"]),
        expected_coarse_plan_sha256=TASK035D_LOCAL_H_PLAN_FILE_SHA256,
        expected_enriched_plan_sha256=(TASK035D_SELECTIVE_FACE_PLAN_FILE_SHA256),
        expected_coarse_manifest_sha256=str(coarse_manifest_sha),
        expected_significant_channel_authority_sha256=(SIGNIFICANT_REFERENCE_SHA256),
    )
    embedded_gate = _mapping(
        evidence.get("independent_checker"),
        "embedded selective-face DWR checker",
    )
    _require(
        gate == embedded_gate,
        "embedded and recomputed selective-face DWR Gates differ",
    )
    return {
        "schema_version": ("task035d.case097-selective-face-dwr-evidence.v1"),
        "path": _path_from_root(path),
        "sha256": observed_sha,
        "report_status": report.get("status"),
        "report_pass": report.get("pass"),
        "report_controlled_negative": report.get("controlled_negative"),
        "coarse_manifest_path": _path_from_root(coarse_manifest_path),
        "coarse_manifest_sha256": coarse_manifest_sha,
        "independent_checker": gate,
        "pass": gate["pass"] is True,
    }


def _csv_float(row: Mapping[str, str], key: str) -> float | None:
    value = row.get(key)
    if value is None or value.strip() == "":
        return None
    try:
        result = float(value)
    except ValueError as error:
        raise Task035dEvidenceError(
            f"timeline {key} is not numeric: {value}"
        ) from error
    _require(math.isfinite(result), f"timeline {key} is not finite")
    return result


def _timeline_resource_metrics(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    _require(bool(rows), "candidate memory timeline is empty")

    def maximum(key: str) -> float | None:
        values = [value for row in rows if (value := _csv_float(row, key)) is not None]
        return max(values) if values else None

    process_rss = maximum("mpi_process_tree_rss_mb")
    process_swap = maximum("mpi_process_tree_swap_mb")
    worker_rss = maximum("worker_rank_rss_sum_mb")
    worker_pss = maximum("worker_rank_pss_sum_mb")
    worker_uss = maximum("worker_rank_uss_sum_mb")
    worker_smaps_swap = maximum("worker_rank_smaps_swap_sum_mb")
    cgroup_current = maximum("container_cgroup_current_mb")
    cgroup_peak = maximum("container_cgroup_peak_mb")
    _require(
        all(
            value is not None
            for value in (
                process_rss,
                process_swap,
                worker_rss,
                worker_pss,
                worker_uss,
                worker_smaps_swap,
                cgroup_current,
                cgroup_peak,
            )
        ),
        "candidate timeline lacks required RSS/PSS/USS/cgroup fields",
    )

    dedicated_rows = [
        row
        for row in rows
        if str(row.get("job_cgroup_dedicated", "")).lower() in {"true", "1"}
    ]
    dedicated_current = max(
        (
            value
            for row in dedicated_rows
            if (value := _csv_float(row, "container_cgroup_current_mb")) is not None
        ),
        default=None,
    )
    dedicated_swap = max(
        (
            value
            for row in dedicated_rows
            if (value := _csv_float(row, "container_swap_current_mb")) is not None
        ),
        default=None,
    )

    expected_ranks = set(range(EXPECTED_MPI_SIZE))
    per_rank_peaks: dict[str, dict[str, float]] = {}
    fully_readable_samples = 0
    maximum_worker_count = 0
    for index, row in enumerate(rows):
        try:
            workers = json.loads(row.get("worker_rank_rss_mb_json") or "[]")
            smaps = json.loads(row.get("worker_rank_smaps_rollup_json") or "[]")
        except json.JSONDecodeError as error:
            raise Task035dEvidenceError(
                f"timeline row {index} contains invalid rank JSON"
            ) from error
        _require(
            isinstance(workers, list) and isinstance(smaps, list),
            f"timeline row {index} rank ledgers must be arrays",
        )
        maximum_worker_count = max(maximum_worker_count, len(workers))
        for item in smaps:
            if not isinstance(item, Mapping) or not isinstance(
                item.get("rank"),
                int,
            ):
                continue
            peak = per_rank_peaks.setdefault(str(item["rank"]), {})
            for name in (
                "rss_mb",
                "pss_mb",
                "uss_mb",
                "shared_mb",
                "anonymous_mb",
                "swap_mb",
                "swap_pss_mb",
            ):
                value = item.get(name)
                if isinstance(value, (int, float)):
                    peak[name] = max(peak.get(name, 0.0), float(value))
        readable = _csv_float(row, "worker_rank_smaps_readable_count")
        if readable != float(EXPECTED_MPI_SIZE):
            continue
        smaps_by_rank = {
            item.get("rank"): item for item in smaps if isinstance(item, Mapping)
        }
        _require(
            set(smaps_by_rank) == expected_ranks,
            f"timeline row {index} does not contain all MPI8 smaps ranks",
        )
        reconstructed: dict[str, float] = {}
        for name in ("pss_mb", "uss_mb", "shared_mb", "swap_mb"):
            reconstructed[name] = sum(
                _finite(
                    smaps_by_rank[rank].get(name),
                    f"timeline row {index} rank {rank} {name}",
                )
                for rank in expected_ranks
            )
        for ledger_key, name in (
            ("worker_rank_pss_sum_mb", "pss_mb"),
            ("worker_rank_uss_sum_mb", "uss_mb"),
            ("worker_rank_shared_sum_mb", "shared_mb"),
            ("worker_rank_smaps_swap_sum_mb", "swap_mb"),
        ):
            _same_number(
                _csv_float(row, ledger_key),
                reconstructed[name],
                context=f"timeline row {index} {ledger_key}",
                tolerance=1.0e-6,
            )
        worker_rss_sum = _finite(
            _csv_float(row, "worker_rank_rss_sum_mb"),
            f"timeline row {index} worker rank RSS sum",
        )
        _require(
            reconstructed["uss_mb"] <= reconstructed["pss_mb"] <= worker_rss_sum,
            f"timeline row {index} violates USS <= PSS <= RSS",
        )
        fully_readable_samples += 1

    _require(
        fully_readable_samples > 0
        and set(per_rank_peaks) == {str(rank) for rank in expected_ranks},
        "candidate timeline has no fully readable MPI8 smaps sample",
    )
    memory_authority_mb = max(
        float(process_rss),
        float(dedicated_current or 0.0),
    )
    zero_swap = bool(
        float(process_swap) == 0.0
        and float(worker_smaps_swap) == 0.0
        and (dedicated_swap is None or float(dedicated_swap) == 0.0)
        and all(values.get("swap_mb") == 0.0 for values in per_rank_peaks.values())
    )
    return {
        "sample_count": len(rows),
        "fully_readable_mpi8_smaps_sample_count": fully_readable_samples,
        "max_observed_worker_rank_count": maximum_worker_count,
        "max_simultaneous_worker_rss_mb": worker_rss,
        "max_simultaneous_worker_pss_mb": worker_pss,
        "max_simultaneous_worker_uss_mb": worker_uss,
        "max_simultaneous_worker_smaps_swap_mb": worker_smaps_swap,
        "max_process_tree_rss_mb": process_rss,
        "max_process_tree_swap_mb": process_swap,
        "dedicated_job_cgroup_observed": bool(dedicated_rows),
        "max_dedicated_cgroup_current_mb": dedicated_current,
        "max_dedicated_cgroup_swap_mb": dedicated_swap,
        "max_container_cgroup_current_observed_mb": cgroup_current,
        "max_container_cgroup_peak_mb": cgroup_peak,
        "per_rank_smaps_rollup_peak_mb": per_rank_peaks,
        "memory_authority_mb": memory_authority_mb,
        "memory_authority_gib": memory_authority_mb / 1024.0,
        "zero_swap": zero_swap,
    }


def _resource_comparison(
    *,
    solver_summary: Mapping[str, Any],
    watchdog_resource: Mapping[str, Any],
    timeline: Mapping[str, Any],
    expected_active_fe_dofs: int = TASK035D_T30_ACTIVE_FE_DOFS,
    expected_solve_rows: int = TASK035D_T30_SOLVE_ROWS,
    candidate_id: str = "t30",
) -> dict[str, Any]:
    for key in (
        "sample_count",
        "fully_readable_mpi8_smaps_sample_count",
        "max_observed_worker_rank_count",
        "max_simultaneous_worker_rss_mb",
        "max_simultaneous_worker_pss_mb",
        "max_simultaneous_worker_uss_mb",
        "max_simultaneous_worker_smaps_swap_mb",
        "max_process_tree_rss_mb",
        "max_process_tree_swap_mb",
        "max_container_cgroup_current_observed_mb",
        "max_container_cgroup_peak_mb",
        "memory_authority_mb",
        "memory_authority_gib",
    ):
        _same_number(
            watchdog_resource.get(key),
            timeline.get(key),
            context=f"watchdog/timeline {key}",
            tolerance=1.0e-6,
        )
    _require(
        watchdog_resource.get("per_rank_smaps_rollup_peak_mb")
        == timeline.get("per_rank_smaps_rollup_peak_mb"),
        "watchdog/timeline per-rank smaps peaks differ",
    )

    matrix = _mapping(solver_summary.get("matrix_stats"), "candidate matrix")
    factor = _mapping(
        (
            _mapping(
                solver_summary.get("stage4_dtn_factor_inventory"),
                "candidate factor inventory",
            )
        ).get("matrix_stats"),
        "candidate factor matrix",
    )
    rows = int(_finite(matrix.get("matrix_rows"), "candidate rows"))
    matrix_nnz = int(_finite(matrix.get("matrix_nnz_used"), "candidate matrix NNZ"))
    factor_nnz = int(_finite(factor.get("matrix_nnz_used"), "candidate factor NNZ"))
    peak_gib = _finite(
        timeline.get("memory_authority_gib"),
        "candidate memory authority GiB",
    )
    checks = {
        "active_fe_dofs_le_90000": (
            solver_summary.get("num_actual_conforming_active_fe_dofs")
            == expected_active_fe_dofs
            and expected_active_fe_dofs <= 90_000
        ),
        f"condensed_rows_match_{candidate_id}": rows == expected_solve_rows,
        "active_rows_decrease": rows < STATIC_P6_ROWS,
        "matrix_nnz_decrease": matrix_nnz < STATIC_P6_MATRIX_NNZ,
        "factor_nnz_decrease": factor_nnz < STATIC_P6_FACTOR_NNZ,
        "mandatory_peak_reduction_ge_20_percent": (peak_gib <= MANDATORY_PEAK_GIB),
        "zero_swap": timeline.get("zero_swap") is True,
        "mpi8_pss_uss_complete": (
            timeline.get("fully_readable_mpi8_smaps_sample_count", 0) > 0
            and timeline.get("max_observed_worker_rank_count") == EXPECTED_MPI_SIZE
            and set((timeline.get("per_rank_smaps_rollup_peak_mb") or {}).keys())
            == {str(rank) for rank in range(EXPECTED_MPI_SIZE)}
        ),
        "cgroup_ledger_present": (
            isinstance(
                timeline.get("max_container_cgroup_current_observed_mb"),
                (int, float),
            )
            and isinstance(
                timeline.get("max_container_cgroup_peak_mb"),
                (int, float),
            )
        ),
    }
    return {
        "schema_version": "task035d.case097-resource-comparison.v1",
        "candidate_id": candidate_id,
        "baseline": {
            "source": "Case096 p6/h10 Full3D static MPI8",
            "active_rows": STATIC_P6_ROWS,
            "matrix_nnz": STATIC_P6_MATRIX_NNZ,
            "factor_nnz": STATIC_P6_FACTOR_NNZ,
            "peak_memory_gib": STATIC_P6_PEAK_GIB,
        },
        "candidate": {
            "active_fe_dofs": solver_summary.get(
                "num_actual_conforming_active_fe_dofs"
            ),
            "active_rows": rows,
            "matrix_nnz": matrix_nnz,
            "factor_nnz": factor_nnz,
            "factor_fill": factor_nnz / matrix_nnz,
            "peak_memory_gib": peak_gib,
            "worker_pss_peak_gib": (
                _finite(
                    timeline.get("max_simultaneous_worker_pss_mb"),
                    "candidate PSS peak",
                )
                / 1024.0
            ),
            "worker_uss_peak_gib": (
                _finite(
                    timeline.get("max_simultaneous_worker_uss_mb"),
                    "candidate USS peak",
                )
                / 1024.0
            ),
        },
        "savings": {
            "active_rows_fraction": 1.0 - rows / STATIC_P6_ROWS,
            "matrix_nnz_fraction": 1.0 - matrix_nnz / STATIC_P6_MATRIX_NNZ,
            "factor_nnz_fraction": 1.0 - factor_nnz / STATIC_P6_FACTOR_NNZ,
            "peak_memory_fraction": 1.0 - peak_gib / STATIC_P6_PEAK_GIB,
        },
        "mandatory_peak_limit_gib": MANDATORY_PEAK_GIB,
        "preferred_peak_limit_gib": PREFERRED_PEAK_GIB,
        "preferred_peak_reduction_ge_40_percent": (peak_gib <= PREFERRED_PEAK_GIB),
        "timeline_reconstruction": dict(timeline),
        "checks": checks,
        "pass": all(checks.values()),
    }


def _energy_comparison(
    candidate: Mapping[str, Any],
    coarse: Mapping[str, Any],
    enriched: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_volume = _finite(
        candidate.get("A_volume_total"),
        "candidate A_volume_total",
    )
    p5_volume = _finite(coarse.get("A_volume_total"), "p5 A_volume_total")
    p6_volume = _finite(
        enriched.get("A_volume_total"),
        "p6 A_volume_total",
    )
    tolerance = max(abs(p6_volume - p5_volume), 1.0e-12)
    volume_error = abs(candidate_volume - p6_volume)
    closure = (
        1.0
        - _finite(candidate.get("R_total"), "candidate R_total")
        - _finite(candidate.get("T_total"), "candidate T_total")
    )
    closure_error = abs(closure - candidate_volume)
    reported = _finite(
        candidate.get("energy_closure_error_port_volume"),
        "candidate reported energy closure",
    )
    r00_sum_error = abs(
        _finite(candidate.get("R00_total"), "candidate R00_total")
        - _finite(candidate.get("R00_s"), "candidate R00_s")
        - _finite(candidate.get("R00_p"), "candidate R00_p")
    )
    checks = {
        "Avolume_same_code_band": volume_error <= tolerance,
        "Aclosure_matches_Avolume": (closure_error <= ENERGY_CLOSURE_TOLERANCE),
        "reported_energy_closure": (abs(reported) <= ENERGY_CLOSURE_TOLERANCE),
        "reported_energy_closure_matches_reconstruction": math.isclose(
            abs(reported),
            closure_error,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "R00_total_is_s_plus_p": r00_sum_error <= 1.0e-12,
    }
    return {
        "schema_version": "task035d.case097-energy-comparison.v1",
        "candidate_A_volume": candidate_volume,
        "global_p5_A_volume": p5_volume,
        "global_p6_A_volume": p6_volume,
        "candidate_vs_p6_absolute_error": volume_error,
        "same_code_p5p6_tolerance": tolerance,
        "candidate_A_closure": closure,
        "A_closure_minus_A_volume_absolute": closure_error,
        "reported_energy_closure_error": reported,
        "R00_s_plus_p_identity_absolute_error": r00_sum_error,
        "checks": checks,
        "pass": all(checks.values()),
    }


def evaluate_task035d_case097_candidate(
    *,
    watchdog: Mapping[str, Any],
    launch_gate: Mapping[str, Any],
    solver_gate: Mapping[str, Any],
    channel_comparison: Mapping[str, Any],
    observable_comparison: Mapping[str, Any],
    energy_comparison: Mapping[str, Any],
    field_comparison: Mapping[str, Any],
    resource_comparison: Mapping[str, Any],
    actual_channel_dwr: Mapping[str, Any] | None = None,
    candidate_id: str = "t30",
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    actual_channel_dwr = (
        actual_channel_dwr if isinstance(actual_channel_dwr, Mapping) else {}
    )
    qualification = _mapping(
        watchdog.get("qualification"),
        "candidate watchdog qualification",
    )
    checks = {
        "watchdog_completed_without_termination": (
            watchdog.get("return_code") == 0
            and watchdog.get("terminated_for_memory") is False
            and watchdog.get("terminated_for_timeout") is False
            and watchdog.get("terminated_for_authority_unreadable") is False
        ),
        "watchdog_structural_qualification": (qualification.get("pass") is True),
        "launch_authority": launch_gate.get("pass") is True,
        "solver_identity_and_residual": solver_gate.get("pass") is True,
        "significant_12_power_and_12_amplitude": (
            channel_comparison.get("pass") is True
            and channel_comparison.get("significant_power_pass_count") == 12
            and channel_comparison.get("significant_complex_amplitude_pass_count") == 12
        ),
        "R00_R_T_Aclosure": observable_comparison.get("pass") is True,
        "Avolume_and_energy_closure": energy_comparison.get("pass") is True,
        "selected_field_and_interface": field_comparison.get("pass") is True,
        "rows_nnz_factor_memory": resource_comparison.get("pass") is True,
        "actual_cross_trace_36_goal_dwr": (
            not spec.get("requires_actual_channel_dwr")
            or actual_channel_dwr.get("pass") is True
        ),
        "ordinary_default_unchanged": (
            solver_gate.get("checks", {}).get(spec["ordinary_default_check"]) is True
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": spec["check_schema"],
        "status": (spec["pass_status"] if not failures else spec["negative_status"]),
        "classification": (
            spec["classification_pass"] if not failures else "controlled_negative"
        ),
        "checks": checks,
        "failures": failures,
        "channel_comparison": dict(channel_comparison),
        "observable_comparison": dict(observable_comparison),
        "energy_comparison": dict(energy_comparison),
        "field_comparison": dict(field_comparison),
        "resource_comparison": dict(resource_comparison),
        "actual_channel_dwr": dict(actual_channel_dwr),
        "pass": not failures,
        "candidate_id": candidate_id,
        "ordinary_default_changed": False,
    }
    if spec["selection_credit"] is not None:
        selection_credit = dict(spec["selection_credit"])
        if spec.get("requires_actual_channel_dwr"):
            selection_credit.update(
                {
                    "actual_channel_dwr": not failures,
                    "goal_oriented_selection_credit": False,
                    "posthoc_actual_action_attribution": not failures,
                    "complete_combined_hp_credit": False,
                }
            )
        result["selection_credit"] = selection_credit
        if "complete_combined_hp_credit" in selection_credit:
            result["complete_combined_hp_credit"] = bool(
                selection_credit["complete_combined_hp_credit"]
            )
    return result


def build_task035d_case097_candidate_check(
    *,
    watchdog_path: Path,
    watchdog_sha256: str,
    field_comparator: Callable[..., dict[str, Any]] = (compare_cross_mesh_fields),
    candidate_id: str = "t30",
) -> dict[str, Any]:
    spec = _candidate_spec(candidate_id)
    checker_source = _checker_source_provenance()
    authorities = _load_frozen_authorities()
    candidate = _load_candidate_raw(
        watchdog_path,
        watchdog_sha256,
        candidate_id=candidate_id,
    )
    watchdog = candidate["record"]
    summary = candidate["solver_summary"]
    actual_channel_dwr = (
        _load_selective_face_dwr_evidence(
            candidate,
            significant_channel_authority=authorities["significant"],
        )
        if spec.get("requires_actual_channel_dwr")
        else {}
    )

    plan, _ = _load_json(
        ROOT / spec["plan_path"],
        expected_sha256=spec["plan_file_sha256"],
        context=spec["plan_context"],
    )
    authority, _ = _load_json(
        ROOT / spec["authority_path"],
        expected_sha256=spec["authority_file_sha256"],
        context=spec["authority_context"],
    )
    launch_gate = spec["plan_gate"](
        plan,
        authority,
        expected_plan_file_sha256=spec["plan_file_sha256"],
        observed_plan_file_sha256=spec["plan_file_sha256"],
        expected_authority_sha256=spec["authority_file_sha256"],
        observed_authority_sha256=spec["authority_file_sha256"],
        plan_is_tracked=_git_tracked(ROOT / spec["plan_path"]),
        authority_is_tracked=_git_tracked(ROOT / spec["authority_path"]),
        plan_path_from_root=spec["plan_path"],
        authority_path_from_root=spec["authority_path"],
    )
    embedded_launch = candidate["launch_contract"]["embedded_launch_gate"]
    for key in (
        "schema_version",
        "status",
        "pass",
        "checks",
        "failures",
        "plan_identity",
        "accuracy_credit",
        "ordinary_default_changed",
    ):
        _require(
            embedded_launch.get(key) == launch_gate.get(key),
            f"embedded/recomputed launch gate mismatch: {key}",
        )
    if spec["selection_credit"] is not None:
        _require(
            embedded_launch.get("selection_credit")
            == launch_gate.get("selection_credit"),
            "embedded/recomputed launch gate mismatch: selection_credit",
        )
    solver_gate = spec["solver_gate"](summary)
    channel_comparison = compare_significant_channels_to_reference_v1(
        candidate_path=candidate["dtn_orders_path"],
        reference_record_path=SIGNIFICANT_REFERENCE_PATH,
        reference_record_sha256=SIGNIFICANT_REFERENCE_SHA256,
    )
    p5p6 = authorities["p5p6"]
    coarse = _mapping(p5p6.get("coarse"), "global p5 control")
    enriched = _mapping(p5p6.get("enriched"), "global p6 reference")
    observable_comparison = compare_observables(
        dict(summary),
        dict(coarse),
        dict(enriched),
    )
    energy_comparison = _energy_comparison(summary, coarse, enriched)
    p5_dir, p6_dir, control_field_artifacts = _control_field_directories(authorities)
    field_comparison = field_comparator(
        global_p5_dir=p5_dir,
        global_p6_dir=p6_dir,
        candidate_p6_dir=candidate["run_dir"],
    )
    timeline = _timeline_resource_metrics(candidate["timeline_path"])
    resource = _mapping(
        watchdog.get("resource_authority"),
        "candidate watchdog resource authority",
    )
    resource_comparison = _resource_comparison(
        solver_summary=summary,
        watchdog_resource=resource,
        timeline=timeline,
        expected_active_fe_dofs=spec["active_fe_dofs"],
        expected_solve_rows=spec["solve_rows"],
        candidate_id=candidate_id,
    )
    result = evaluate_task035d_case097_candidate(
        watchdog=watchdog,
        launch_gate=launch_gate,
        solver_gate=solver_gate,
        channel_comparison=channel_comparison,
        observable_comparison=observable_comparison,
        energy_comparison=energy_comparison,
        field_comparison=field_comparison,
        resource_comparison=resource_comparison,
        actual_channel_dwr=actual_channel_dwr,
        candidate_id=candidate_id,
    )
    original_qualification = _mapping(
        watchdog.get("qualification"),
        "candidate watchdog qualification",
    )
    original_false_checks = sorted(
        str(name)
        for name, passed in _mapping(
            original_qualification.get("checks"),
            "candidate watchdog qualification checks",
        ).items()
        if passed is not True
    )
    checker_contract_false_negative = bool(
        candidate_id == TASK035D_LOCAL_H_PLAN_NAME
        and original_false_checks == ["task035d_solver_local_h_backend_actual"]
        and solver_gate.get("pass") is True
    )
    result.update(
        {
            "benchmark_id": spec["benchmark_id"],
            "source_sha": candidate["source_sha"],
            "checker_source": checker_source,
            "candidate_watchdog": {
                "path": _path_from_root(candidate["record_path"]),
                "sha256": candidate["record_sha256"],
            },
            "raw_artifacts": candidate["artifacts"],
            "frozen_authorities": authorities["authorities"],
            "control_field_artifacts": control_field_artifacts,
            "launch_gate": launch_gate,
            "candidate_launch_contract": candidate["launch_contract"],
            "solver_gate": solver_gate,
            "watchdog_checker_requalification": {
                "schema_version": ("task035d.watchdog-checker-requalification.v1"),
                "original_watchdog_pass": (original_qualification.get("pass")),
                "original_false_checks": original_false_checks,
                "current_solver_gate_pass": solver_gate.get("pass"),
                "current_solver_gate_failures": solver_gate.get("failures"),
                "checker_contract_false_negative": (checker_contract_false_negative),
                "numerical_kernel_rerun_required": False,
                "candidate_physical_status_is_not_changed": True,
            },
            "accuracy_credit": (
                spec["pass_accuracy_credit"]
                if result["pass"]
                else "none_controlled_negative_preserved"
            ),
        }
    )
    return result


def compact_task035d_case097_candidate_check(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Trim a full candidate check without removing any acceptance Gate."""

    field = _mapping(
        result.get("field_comparison"),
        "candidate field comparison",
    )
    selections = _mapping(
        field.get("selections"),
        "candidate field selections",
    )
    compact_selections: dict[str, Any] = {}
    for name in ("volume", "interface"):
        row = _mapping(
            selections.get(name),
            f"candidate field selection {name}",
        )
        compact_selections[name] = {
            key: row.get(key)
            for key in (
                "probe_count",
                "probe_sha256",
                "region_counts",
                "global_p5_vs_p6_weighted_relative_l2",
                "candidate_vs_p6_weighted_relative_l2",
                "same_code_p5p6_weighted_relative_l2_tolerance",
                "global_p5_vs_p6_max_pointwise_absolute_error",
                "candidate_vs_p6_max_pointwise_absolute_error",
                "same_code_p5p6_max_pointwise_tolerance",
                "weighted_relative_l2_pass",
                "maximum_pointwise_pass",
                "pass",
            )
        }
    resource = _mapping(
        result.get("resource_comparison"),
        "candidate resource comparison",
    )
    timeline = _mapping(
        resource.get("timeline_reconstruction"),
        "candidate timeline reconstruction",
    )
    compact_resource = {
        key: resource.get(key)
        for key in (
            "schema_version",
            "candidate_id",
            "baseline",
            "candidate",
            "savings",
            "mandatory_peak_limit_gib",
            "preferred_peak_limit_gib",
            "preferred_peak_reduction_ge_40_percent",
            "checks",
            "pass",
        )
    }
    compact_resource["telemetry"] = {
        key: timeline.get(key)
        for key in (
            "sample_count",
            "fully_readable_mpi8_smaps_sample_count",
            "max_observed_worker_rank_count",
            "max_simultaneous_worker_rss_mb",
            "max_simultaneous_worker_pss_mb",
            "max_simultaneous_worker_uss_mb",
            "max_simultaneous_worker_smaps_swap_mb",
            "max_process_tree_rss_mb",
            "max_process_tree_swap_mb",
            "dedicated_job_cgroup_observed",
            "max_container_cgroup_current_observed_mb",
            "max_container_cgroup_peak_mb",
            "memory_authority_mb",
            "memory_authority_gib",
            "zero_swap",
        )
    }
    launch = _mapping(
        result.get("launch_gate"),
        "candidate launch gate",
    )
    return {
        "schema_version": ("task035d.case097-candidate-check-compact.v1"),
        "status": result.get("status"),
        "classification": result.get("classification"),
        "candidate_id": result.get("candidate_id"),
        "pass": result.get("pass"),
        "checks": result.get("checks"),
        "failures": result.get("failures"),
        "accuracy_credit": result.get("accuracy_credit"),
        "selection_credit": result.get("selection_credit"),
        "complete_combined_hp_credit": result.get("complete_combined_hp_credit"),
        "actual_channel_dwr": result.get("actual_channel_dwr"),
        "source_sha": result.get("source_sha"),
        "checker_source": result.get("checker_source"),
        "candidate_watchdog": result.get("candidate_watchdog"),
        "raw_artifacts": result.get("raw_artifacts"),
        "frozen_authorities": result.get("frozen_authorities"),
        "launch_identity": {
            "schema_version": launch.get("schema_version"),
            "status": launch.get("status"),
            "pass": launch.get("pass"),
            "plan_identity": launch.get("plan_identity"),
            "selection_credit": launch.get("selection_credit"),
        },
        "solver_gate": result.get("solver_gate"),
        "watchdog_checker_requalification": result.get(
            "watchdog_checker_requalification"
        ),
        "channel_comparison": result.get("channel_comparison"),
        "observable_comparison": result.get("observable_comparison"),
        "energy_comparison": result.get("energy_comparison"),
        "field_comparison": {
            key: field.get(key)
            for key in (
                "schema_version",
                "status",
                "method",
                "no_native_point_intersection",
                "no_probe_dropping",
                "no_threshold_relaxation",
                "relative_l2_floor",
                "maximum_pointwise_floor",
                "pass",
            )
        }
        | {"selections": compact_selections},
        "resource_comparison": compact_resource,
        "production_qualified": result.get("pass") is True,
        "ordinary_default_changed": result.get("ordinary_default_changed"),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Independently check one frozen Task035d Case097 MPI8 candidate.")
    )
    parser.add_argument(
        "--candidate-id",
        choices=(
            "t30",
            "sidewall_z0_guard_v1",
            TASK035D_LOCAL_H_PLAN_NAME,
            TASK035D_COMBINED_HP_PLAN_NAME,
            TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            TASK035D_SELECTIVE_FACE_PLAN_NAME,
        ),
        default="t30",
    )
    parser.add_argument("--watchdog", type=Path, required=True)
    parser.add_argument("--watchdog-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Persist the review-sized hash-bound result.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    spec = _candidate_spec(args.candidate_id)
    output = args.output
    output = output if output.is_absolute() else ROOT / output
    try:
        result = build_task035d_case097_candidate_check(
            watchdog_path=args.watchdog,
            watchdog_sha256=args.watchdog_sha256,
            candidate_id=args.candidate_id,
        )
        if args.compact:
            result = compact_task035d_case097_candidate_check(result)
        return_code = 0 if result["pass"] else 1
    except Exception as error:
        watchdog_path = args.watchdog
        watchdog_path = (
            watchdog_path if watchdog_path.is_absolute() else ROOT / watchdog_path
        )
        result = {
            "schema_version": spec["check_schema"],
            "status": spec["evidence_failure_status"],
            "classification": "fail_closed_evidence_error",
            "candidate_id": args.candidate_id,
            "pass": False,
            "checks": {"evidence_integrity": False},
            "failures": ["evidence_integrity"],
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
            "candidate_watchdog": {
                "path": _path_from_root(watchdog_path),
                "expected_sha256": args.watchdog_sha256,
                "observed_sha256": (
                    _sha256(watchdog_path) if watchdog_path.is_file() else None
                ),
            },
            "accuracy_credit": "none_fail_closed",
            "ordinary_default_changed": False,
        }
        return_code = 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "pass": result["pass"],
                "failures": result["failures"],
                "output": _path_from_root(output),
                "sha256": _sha256(output),
            },
            ensure_ascii=False,
        )
    )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CASE096_AUTHORITY_PATH",
    "CASE096_AUTHORITY_SHA256",
    "ENERGY_CLOSURE_TOLERANCE",
    "FIELD_AUTHORITY_PATH",
    "FIELD_AUTHORITY_SHA256",
    "MANDATORY_PEAK_GIB",
    "P5P6_CONTROL_PATH",
    "P5P6_CONTROL_SHA256",
    "PREFERRED_PEAK_GIB",
    "SIGNIFICANT_REFERENCE_PATH",
    "SIGNIFICANT_REFERENCE_SHA256",
    "Task035dEvidenceError",
    "_energy_comparison",
    "_resource_comparison",
    "_timeline_resource_metrics",
    "build_task035d_case097_candidate_check",
    "compact_task035d_case097_candidate_check",
    "evaluate_task035d_case097_candidate",
]
