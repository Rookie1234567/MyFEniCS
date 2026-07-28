from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CASE098 = (
    ROOT
    / "benchmarks"
    / "cases"
    / "098_reference_blind_multilevel_hp_adaptivity"
)


class Task035eCase098EvidenceError(ValueError):
    """Raised when Case098 evidence or a completion claim fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task035eCase098EvidenceError(message)


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
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value)),
        f"{context} must be a finite number",
    )
    return float(value)


def _integer(value: Any, context: str) -> int:
    number = _finite(value, context)
    _require(number.is_integer(), f"{context} must be an integer")
    return int(number)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, context: str) -> Mapping[str, Any]:
    _require(path.is_file(), f"{context} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Task035eCase098EvidenceError(
            f"{context} is not valid JSON: {error}",
        ) from error
    return _mapping(value, context)


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    context: str,
) -> None:
    observed = set(value)
    _require(
        observed == expected,
        f"{context} keys differ: missing={sorted(expected - observed)}, "
        f"extra={sorted(observed - expected)}",
    )


def _validate_schema_is_closed(schema: Mapping[str, Any]) -> None:
    def walk(value: Any, context: str) -> None:
        if isinstance(value, Mapping):
            if value.get("type") == "object":
                _require(
                    value.get("additionalProperties") is False,
                    f"{context} object schema is not fail-closed",
                )
            for key, child in value.items():
                walk(child, f"{context}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{context}[{index}]")

    walk(schema, "schema")


def _validate_expected(expected: Mapping[str, Any]) -> None:
    _exact_keys(
        expected,
        {
            "schema_version",
            "case_id",
            "initial_classification",
            "formal_mpi_size",
            "reference",
            "goals",
            "blind_adaptivity",
            "full3d_resource",
            "hybrid",
            "initial_completion_pass",
            "initial_numerical_credit",
            "ordinary_default_changed",
        },
        "expected",
    )
    _require(
        expected["schema_version"] == "task035e.case098-expected.v1",
        "expected schema_version is invalid",
    )
    _require(
        expected["case_id"]
        == "098_reference_blind_multilevel_hp_adaptivity",
        "expected case_id is invalid",
    )
    _exact_keys(
        _mapping(expected["reference"], "expected.reference"),
        {
            "degree",
            "h_nm",
            "full_explicit_true_residual_max",
            "energy_identity_error_max",
            "absorption_identity_error_max",
            "h5_physical_memory_free_fraction_min",
            "swap_gib_max",
        },
        "expected.reference",
    )
    _exact_keys(
        _mapping(expected["goals"], "expected.goals"),
        {
            "ports",
            "n",
            "m",
            "orders_per_port",
            "power_goal_count",
            "complex_amplitude_goal_count",
            "amplitude_real_goal_count",
            "minimum_order_real_goal_count",
        },
        "expected.goals",
    )
    _exact_keys(
        _mapping(expected["blind_adaptivity"], "expected.blind_adaptivity"),
        {
            "path_a_h_nm",
            "path_b_h_nm",
            "maximum_cycles_per_path",
            "production_degrees",
            "minimum_local_refinement_levels",
            "minimum_separated_patches",
            "maximum_adjacent_level_jump",
            "maximum_normalized_shadow_delta",
            "two_start_max_normalized_difference",
        },
        "expected.blind_adaptivity",
    )
    _exact_keys(
        _mapping(expected["full3d_resource"], "expected.full3d_resource"),
        {
            "active_rows_max_exclusive",
            "matrix_nnz_max_exclusive",
            "factor_nnz_max_exclusive",
            "solver_phase_peak_baseline_gib",
            "solver_phase_peak_mandatory_gib",
            "solver_phase_peak_preferred_gib",
            "swap_gib_max",
        },
        "expected.full3d_resource",
    )
    _exact_keys(
        _mapping(expected["hybrid"], "expected.hybrid"),
        {
            "initial_mode_count",
            "power_pass_required",
            "complex_amplitude_pass_required",
            "solver_phase_peak_baseline_gib",
            "solver_phase_peak_preferred_gib",
            "swap_gib_max",
        },
        "expected.hybrid",
    )


def _resolve_evidence_path(
    raw_path: str,
    case_dir: Path,
    context: str,
) -> Path:
    path = Path(raw_path)
    _require(not path.is_absolute(), f"{context}.path must be relative")
    _require(".." not in path.parts, f"{context}.path may not escape its root")
    candidates = (ROOT / path, case_dir / path)
    for candidate in candidates:
        if candidate.is_file():
            resolved = candidate.resolve()
            allowed_roots = (ROOT.resolve(), case_dir.resolve())
            _require(
                any(
                    resolved == root or root in resolved.parents
                    for root in allowed_roots
                ),
                f"{context}.path resolves outside allowed roots",
            )
            return resolved
    raise Task035eCase098EvidenceError(
        f"{context}.path does not exist: {raw_path}",
    )


def _record_source_shas(record: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("source_sha", "source_commit_sha", "numerical_source_sha"):
        value = record.get(key)
        if isinstance(value, str):
            values.add(value)
    for parent_name in ("source", "metadata"):
        parent = record.get(parent_name)
        if isinstance(parent, Mapping):
            for key in (
                "commit_sha",
                "source_sha",
                "source_commit_sha",
                "verified_clean_sha",
            ):
                value = parent.get(key)
                if isinstance(value, str):
                    values.add(value)
    return values


def _validate_evidence_role(
    record: Mapping[str, Any],
    *,
    role: str,
    context: str,
) -> None:
    """Reject generic/dummy JSON; every authority must use its role schema."""

    schema = record.get("schema_version")
    if role.startswith("layer:"):
        _exact_keys(
            record,
            {
                "schema_version",
                "role",
                "module_path",
                "source_sha",
                "files",
                "package_sha256",
            },
            f"{context} layer package manifest",
        )
        _require(
            schema == "task035e.layer-package-manifest.v1",
            f"{context} layer package manifest schema is unsupported",
        )
        _require(
            record["role"] == role.removeprefix("layer:"),
            f"{context} layer package role is wrong",
        )
        files = _sequence(record["files"], f"{context}.files")
        _require(files, f"{context} layer package manifest is empty")
        for index, item in enumerate(files):
            row = _mapping(item, f"{context}.files[{index}]")
            _exact_keys(
                row,
                {"path", "sha256"},
                f"{context}.files[{index}]",
            )
            _require(
                isinstance(row["path"], str) and bool(row["path"]),
                f"{context}.files[{index}].path is invalid",
            )
            _require(
                isinstance(row["sha256"], str)
                and len(row["sha256"]) == 64,
                f"{context}.files[{index}].sha256 is invalid",
            )
        return
    if role.startswith("reference_run:"):
        _require(
            schema == "task033.full3d-watchdog.v1",
            f"{context} is not a Full3D watchdog authority",
        )
        expected_h = {
            "reference_run:p6_h10": 10.0,
            "reference_run:p6_h7p5": 7.5,
            "reference_run:p6_h5": 5.0,
        }[role]
        _require(
            record.get("degree") == 6
            and _finite(record.get("h_nm"), f"{context}.h_nm") == expected_h
            and record.get("run_kind") == "full-solve"
            and record.get("mpi_size") == 8
            and record.get("status")
            in {
                "task035e_reference_full_solve_pass",
                "controlled_resource_stop",
            },
            f"{context} is not a Task035e reference full-solve authority",
        )
        qualification = _mapping(
            record.get("qualification"),
            f"{context}.qualification",
        )
        if record.get("status") == "task035e_reference_full_solve_pass":
            _require(
                qualification.get("pass") is True
                and record.get("no_swap") is True,
                f"{context} reference full solve did not pass",
            )
        task035e = _mapping(
            record.get("task035e_reference_certifier"),
            f"{context}.task035e_reference_certifier",
        )
        _require(
            task035e.get("schema_version")
            == "task035e.reference-resource-authority.v1"
            and task035e.get("selected") is True,
            f"{context} lacks the Task035e resource authority",
        )
        return
    expected_schema = {
        "reference_convergence": (
            "task035e.sealed-hidden-reference-package.v1"
        ),
        "reference_isolation": "task035e.reference-leak-check.v1",
        "blind_cycle": "task035e.blind-cycle-evidence.v1",
        "blind_final": "task035e.blind-final-authority.v1",
        "two_start": "task035e.two-path-freeze-gate.v1",
        "hidden_audit": "task035e.final-hidden-audit.v1",
        "full3d_resource": "task035e.full3d-resource-authority.v1",
        "hybrid_gate": "task035e.hybrid-gate-authority.v1",
        "hybrid_resource": "task035e.hybrid-resource-authority.v1",
    }.get(role)
    _require(expected_schema is not None, f"{context} has an unknown evidence role")
    _require(
        schema == expected_schema,
        f"{context} evidence schema is not valid for role {role}",
    )
    if role == "reference_convergence":
        certification = _mapping(
            record.get("certification"),
            f"{context}.certification",
        )
        _require(
            certification.get("qualified") is True
            and certification.get("status") == "qualified"
            and certification.get("gates", {}).get("passed") is True,
            f"{context} sealed reference is not qualified",
        )
    elif role == "reference_isolation":
        checks = _mapping(record.get("checks"), f"{context}.checks")
        dynamic = _mapping(checks.get("dynamic"), f"{context}.checks.dynamic")
        _require(
            record.get("pass") is True
            and record.get("status") == "reference_isolation_pass"
            and dynamic.get("pass") is True
            and dynamic.get("status") == "audit_pass",
            f"{context} lacks a formal dynamic isolation pass",
        )
    elif role == "two_start":
        _require(
            record.get("pass") is True,
            f"{context} two-start authority did not pass",
        )
    elif role == "hidden_audit":
        from src.adaptivity.hidden_auditor import (
            validate_hidden_audit_payload,
        )

        validate_hidden_audit_payload(record)
    else:
        _require(
            record.get("status") in {"completed", "freeze_ready", "frozen"},
            f"{context} role authority does not carry a completed status",
        )


def _validate_pointer(
    value: Any,
    case_dir: Path,
    expected_source_sha: str | None,
    context: str,
    *,
    role: str,
) -> bool:
    pointer = _mapping(value, context)
    status = pointer["status"]
    metadata = (pointer["path"], pointer["sha256"], pointer["source_sha"])
    if status == "not_run":
        _require(
            metadata == (None, None, None),
            f"{context} not_run pointer must not contain path or hashes",
        )
        return False

    _require(
        all(isinstance(item, str) for item in metadata),
        f"{context} {status} pointer must bind path, SHA-256, and source SHA",
    )
    raw_path, expected_sha256, source_sha = metadata
    _require(
        expected_source_sha is not None,
        f"{context} has evidence but campaign source_commit_sha is null",
    )
    _require(
        source_sha == expected_source_sha,
        f"{context}.source_sha differs from campaign source_commit_sha",
    )
    evidence_path = _resolve_evidence_path(raw_path, case_dir, context)
    observed_sha256 = _sha256(evidence_path)
    _require(
        observed_sha256 == expected_sha256,
        f"{context} SHA-256 mismatch: expected {expected_sha256}, "
        f"got {observed_sha256}",
    )
    record = _load_json(evidence_path, f"{context} record")
    record_shas = _record_source_shas(record)
    _require(record_shas, f"{context} record has no source SHA")
    _require(
        record_shas == {source_sha},
        f"{context} record source SHA fields disagree with pointer",
    )
    _validate_evidence_role(record, role=role, context=f"{context} record")
    return status == "completed"


def _validate_layer_packages(
    config: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
) -> dict[str, bool]:
    layers = _mapping(config["layer_packages"], "config.layer_packages")
    expected_paths = {
        "reference_certifier": "src/adaptivity/reference_certifier",
        "blind_controller": "src/adaptivity/blind_controller",
        "hidden_auditor": "src/adaptivity/hidden_auditor",
    }
    result: dict[str, bool] = {}
    for name, module_path in expected_paths.items():
        layer = _mapping(layers[name], f"config.layer_packages.{name}")
        _require(
            layer["module_path"] == module_path,
            f"config.layer_packages.{name}.module_path is invalid",
        )
        result[name] = _validate_pointer(
            layer["package_manifest"],
            case_dir,
            source_sha,
            f"config.layer_packages.{name}.package_manifest",
            role=f"layer:{name}",
        )
    return result


def _validate_reference_isolation(
    config: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
) -> bool:
    return _validate_pointer(
        config["reference_isolation"],
        case_dir,
        source_sha,
        "config.reference_isolation",
        role="reference_isolation",
    )


def _reference_gate_pass(
    run: Mapping[str, Any],
    expected: Mapping[str, Any],
    context: str,
) -> bool:
    gate = _mapping(run["gate"], f"{context}.gate")
    status = run["status"]
    if status == "not_run":
        _require(
            all(value is None for value in gate.values()),
            f"{context} not_run gate fields must all be null",
        )
        return False
    if status == "controlled_resource_stop":
        _require(
            gate["completed_full_solve"] is not True,
            f"{context} controlled resource stop cannot contain a full solve",
        )
        return False
    if status != "completed":
        return False

    numeric_names = (
        "full_explicit_true_residual",
        "energy_identity_error",
        "absorption_identity_error",
        "physical_memory_free_fraction_after",
        "swap_gib",
    )
    values = {
        name: _finite(gate[name], f"{context}.gate.{name}")
        for name in numeric_names
    }
    pass_gate = (
        gate["completed_full_solve"] is True
        and values["full_explicit_true_residual"]
        <= _finite(
            expected["full_explicit_true_residual_max"],
            "expected.reference.full_explicit_true_residual_max",
        )
        and values["energy_identity_error"]
        <= _finite(
            expected["energy_identity_error_max"],
            "expected.reference.energy_identity_error_max",
        )
        and values["absorption_identity_error"]
        <= _finite(
            expected["absorption_identity_error_max"],
            "expected.reference.absorption_identity_error_max",
        )
        and values["swap_gib"]
        <= _finite(
            expected["swap_gib_max"],
            "expected.reference.swap_gib_max",
        )
    )
    if run["run_id"] == "p6_h5":
        pass_gate = pass_gate and (
            values["physical_memory_free_fraction_after"]
            >= _finite(
                expected["h5_physical_memory_free_fraction_min"],
                "expected.reference.h5_physical_memory_free_fraction_min",
            )
        )
    return pass_gate


def _validate_reference_campaign(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
) -> tuple[bool, dict[str, bool]]:
    campaign = _mapping(
        config["reference_campaign"],
        "config.reference_campaign",
    )
    expected_reference = _mapping(expected["reference"], "expected.reference")
    runs = _sequence(campaign["runs"], "config.reference_campaign.runs")
    expected_identity = {
        "p6_h10": (6, 10.0),
        "p6_h7p5": (6, 7.5),
        "p6_h5": (6, 5.0),
    }
    _require(
        {str(run["run_id"]) for run in runs} == set(expected_identity),
        "reference run IDs are not exactly p6_h10/p6_h7p5/p6_h5",
    )
    results: dict[str, bool] = {}
    for index, value in enumerate(runs):
        run = _mapping(value, f"config.reference_campaign.runs[{index}]")
        run_id = str(run["run_id"])
        expected_degree, expected_h = expected_identity[run_id]
        _require(run["degree"] == expected_degree, f"{run_id} degree is not p6")
        _require(
            _finite(run["h_nm"], f"{run_id}.h_nm") == expected_h,
            f"{run_id} h_nm differs from the fixed campaign",
        )
        pointer_status = _mapping(run["evidence"], f"{run_id}.evidence")[
            "status"
        ]
        _require(
            pointer_status == run["status"],
            f"{run_id} run and evidence statuses differ",
        )
        pointer_complete = _validate_pointer(
            run["evidence"],
            case_dir,
            source_sha,
            f"config.reference_campaign.{run_id}.evidence",
            role=f"reference_run:{run_id}",
        )
        results[run_id] = pointer_complete and _reference_gate_pass(
            run,
            expected_reference,
            f"config.reference_campaign.{run_id}",
        )

    convergence_complete = _validate_pointer(
        campaign["convergence_authority"],
        case_dir,
        source_sha,
        "config.reference_campaign.convergence_authority",
        role="reference_convergence",
    )
    qualified = all(results.values()) and convergence_complete
    _require(
        campaign["qualification_claimed"] is qualified,
        "reference qualification claim differs from raw run and convergence "
        "gates",
    )
    return qualified, results


def _validate_goal_contract(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    goals = _mapping(config["goal_contract"], "config.goal_contract")
    expected_goals = _mapping(expected["goals"], "expected.goals")
    for name in (
        "ports",
        "n",
        "m",
        "orders_per_port",
        "power_goal_count",
        "complex_amplitude_goal_count",
        "amplitude_real_goal_count",
        "minimum_order_real_goal_count",
    ):
        _require(
            goals[name] == expected_goals[name],
            f"config.goal_contract.{name} differs from fixed N=8 contract",
        )
    _require(
        goals["significance_filter_used"] is False,
        "Case098 fixed N=8 contract may not use a significance filter",
    )
    order_count = len(goals["ports"]) * len(goals["m"])
    _require(
        order_count == goals["power_goal_count"] == 16,
        "power goal count is not recomputable as two ports times N=8",
    )
    _require(
        order_count == goals["complex_amplitude_goal_count"] == 16,
        "complex-amplitude goal count is not two ports times N=8",
    )
    _require(
        2 * order_count == goals["amplitude_real_goal_count"] == 32,
        "real amplitude component count is not twice the complex count",
    )
    _require(
        goals["power_goal_count"] + goals["amplitude_real_goal_count"]
        == goals["minimum_order_real_goal_count"]
        == 48,
        "minimum order real-goal count is not 16 powers plus 32 amplitudes",
    )


def _validate_adaptive_contract(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    adaptive = _mapping(config["adaptive_contract"], "config.adaptive_contract")
    target = _mapping(
        expected["blind_adaptivity"],
        "expected.blind_adaptivity",
    )
    for name in (
        "production_degrees",
        "minimum_local_refinement_levels",
        "minimum_separated_patches",
        "maximum_adjacent_level_jump",
        "maximum_normalized_shadow_delta",
    ):
        _require(
            adaptive[name] == target[name],
            f"config.adaptive_contract.{name} differs from Task035e",
        )
    for name in (
        "periodic_closure_required",
        "material_interface_protection_required",
        "hanging_trace_required",
        "mpi_ownership_required",
        "p_shadow_required",
        "h_shadow_required",
    ):
        _require(adaptive[name] is True, f"{name} must remain required")


def _validate_cycle(
    cycle: Mapping[str, Any],
    index: int,
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
    context: str,
) -> bool:
    _require(
        _integer(cycle["cycle_index"], f"{context}.cycle_index") == index,
        f"{context}.cycle_index is not sequential",
    )
    evidence_complete = _validate_pointer(
        cycle["evidence"],
        case_dir,
        source_sha,
        f"{context}.evidence",
        role="blind_cycle",
    )
    _require(
        evidence_complete,
        f"{context} must bind a completed cycle record",
    )
    target = _mapping(
        expected["blind_adaptivity"],
        "expected.blind_adaptivity",
    )
    residual = _finite(
        cycle["full_explicit_true_residual"],
        f"{context}.full_explicit_true_residual",
    )
    energy = _finite(
        cycle["energy_identity_error"],
        f"{context}.energy_identity_error",
    )
    p_shadow = _finite(
        cycle["max_normalized_p_shadow_delta"],
        f"{context}.max_normalized_p_shadow_delta",
    )
    h_shadow = _finite(
        cycle["max_normalized_h_shadow_delta"],
        f"{context}.max_normalized_h_shadow_delta",
    )
    level_counts = _mapping(cycle["level_counts"], f"{context}.level_counts")
    return (
        cycle["accepted"] is True
        and residual <= 1.0e-9
        and energy <= 1.0e-9
        and p_shadow <= target["maximum_normalized_shadow_delta"]
        and h_shadow <= target["maximum_normalized_shadow_delta"]
        and all(_integer(level_counts[str(level)], context) > 0 for level in range(3))
        and cycle["separated_patch_count"]
        >= target["minimum_separated_patches"]
        and cycle["maximum_adjacent_level_jump"]
        <= target["maximum_adjacent_level_jump"]
        and cycle["periodic_closure_pass"] is True
        and cycle["material_interface_pass"] is True
        and cycle["hanging_trace_pass"] is True
        and cycle["mpi_ownership_pass"] is True
    )


def _validate_blind_trials(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
) -> tuple[bool, dict[str, bool]]:
    trials = _mapping(config["blind_trials"], "config.blind_trials")
    target = _mapping(
        expected["blind_adaptivity"],
        "expected.blind_adaptivity",
    )
    _require(
        trials["maximum_cycles_per_path"]
        == target["maximum_cycles_per_path"]
        == 6,
        "blind cycle cap is not six",
    )
    paths = _sequence(trials["paths"], "config.blind_trials.paths")
    expected_paths = {
        "path_a": target["path_a_h_nm"],
        "path_b": target["path_b_h_nm"],
    }
    _require(
        {str(path["path_id"]) for path in paths} == set(expected_paths),
        "blind paths are not exactly path_a and path_b",
    )
    path_pass: dict[str, bool] = {}
    for path_value in paths:
        path = _mapping(path_value, "config.blind_trials.paths[]")
        path_id = str(path["path_id"])
        _require(
            path["nominal_h_nm"] == expected_paths[path_id],
            f"{path_id} nominal h family differs from Task035e",
        )
        cycles = _sequence(path["cycles"], f"{path_id}.cycles")
        _require(len(cycles) <= 6, f"{path_id} exceeds the six-cycle cap")
        if path["status"] == "not_run":
            _require(not cycles, f"{path_id} not_run path contains cycles")
            _require(
                _mapping(path["final_authority"], f"{path_id}.final_authority")[
                    "status"
                ]
                == "not_run",
                f"{path_id} not_run path has a final authority",
            )
        cycle_passes: list[bool] = []
        for offset, cycle_value in enumerate(cycles, start=1):
            cycle = _mapping(cycle_value, f"{path_id}.cycles[{offset - 1}]")
            cycle_passes.append(
                _validate_cycle(
                    cycle,
                    offset,
                    expected,
                    case_dir,
                    source_sha,
                    f"{path_id}.cycles[{offset - 1}]",
                )
            )
        final_complete = _validate_pointer(
            path["final_authority"],
            case_dir,
            source_sha,
            f"{path_id}.final_authority",
            role="blind_final",
        )
        _require(
            (path["status"] == "frozen") is final_complete,
            f"{path_id} frozen status differs from its final authority",
        )
        last_two_stable = len(cycles) >= 2 and all(
            cycle["accepted"] is True
            and cycle["outputs_stable_to_previous"] is True
            for cycle in cycles[-2:]
        )
        p_shadow_verified = any(
            cycle["p_shadow_verified"] is True for cycle in cycles
        )
        h_shadow_verified = any(
            cycle["h_shadow_verified"] is True for cycle in cycles
        )
        path_pass[path_id] = (
            path["status"] == "frozen"
            and final_complete
            and bool(cycle_passes)
            and cycle_passes[-1]
            and last_two_stable
            and p_shadow_verified
            and h_shadow_verified
        )

    comparison = _mapping(
        trials["two_start_comparison"],
        "config.blind_trials.two_start_comparison",
    )
    comparison_complete = _validate_pointer(
        comparison["evidence"],
        case_dir,
        source_sha,
        "config.blind_trials.two_start_comparison.evidence",
        role="two_start",
    )
    difference = comparison["max_normalized_output_difference"]
    _require(
        comparison_complete or difference is None,
        "two-start result has no completed evidence",
    )
    comparison_pass = (
        comparison_complete
        and difference is not None
        and _finite(
            difference,
            "config.blind_trials.two_start_comparison."
            "max_normalized_output_difference",
        )
        <= target["two_start_max_normalized_difference"]
    )
    return all(path_pass.values()) and comparison_pass, path_pass


def _validate_freeze(
    config: Mapping[str, Any],
    source_sha: str | None,
) -> bool:
    freeze = _mapping(config["freeze"], "config.freeze")
    hash_names = (
        "mesh_forest_sha256",
        "degree_map_sha256",
        "output_sha256",
        "internal_certificate_sha256",
        "resource_authority_sha256",
    )
    if freeze["status"] == "not_run":
        _require(
            freeze["candidate_immutable"] is False
            and freeze["source_commit_sha"] is None
            and all(freeze[name] is None for name in hash_names),
            "not_run freeze must not contain immutable identity claims",
        )
        return False
    _require(source_sha is not None, "frozen candidate lacks campaign source SHA")
    return (
        freeze["candidate_immutable"] is True
        and freeze["source_commit_sha"] == source_sha
        and all(isinstance(freeze[name], str) for name in hash_names)
    )


def _validate_hidden_audit(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
    freeze_pass: bool,
) -> bool:
    audit = _mapping(config["hidden_audit"], "config.hidden_audit")
    raw_names = (
        "power_pass_count",
        "complex_amplitude_pass_count",
        "full_propagating_spectrum_pass",
        "total_observables_pass",
        "field_observables_pass",
        "residual_and_energy_pass",
    )
    if audit["status"] == "not_run":
        _require(
            audit["opened_after_freeze"] is False
            and audit["candidate_retuned_after_open"] is False
            and all(audit[name] is None for name in raw_names),
            "not_run hidden audit contains result claims",
        )
    pointer_complete = _validate_pointer(
        audit["evidence"],
        case_dir,
        source_sha,
        "config.hidden_audit.evidence",
        role="hidden_audit",
    )
    _require(
        _mapping(audit["evidence"], "config.hidden_audit.evidence")["status"]
        == audit["status"],
        "hidden-audit and evidence statuses differ",
    )
    goals = _mapping(expected["goals"], "expected.goals")
    return (
        audit["status"] == "completed"
        and pointer_complete
        and freeze_pass
        and audit["opened_after_freeze"] is True
        and audit["candidate_retuned_after_open"] is False
        and audit["power_pass_count"] == goals["power_goal_count"]
        and audit["complex_amplitude_pass_count"]
        == goals["complex_amplitude_goal_count"]
        and audit["full_propagating_spectrum_pass"] is True
        and audit["total_observables_pass"] is True
        and audit["field_observables_pass"] is True
        and audit["residual_and_energy_pass"] is True
    )


def _validate_full3d_resource(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
) -> tuple[bool, bool]:
    resource = _mapping(
        _mapping(config["resource_ledger"], "config.resource_ledger")["full3d"],
        "config.resource_ledger.full3d",
    )
    raw_names = (
        "active_rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_phase_peak_gib",
        "swap_gib",
        "same_mpi_solver_lifecycle_telemetry",
    )
    if resource["status"] == "not_run":
        _require(
            all(resource[name] is None for name in raw_names),
            "not_run Full3D resource ledger contains measurements",
        )
    pointer_complete = _validate_pointer(
        resource["evidence"],
        case_dir,
        source_sha,
        "config.resource_ledger.full3d.evidence",
        role="full3d_resource",
    )
    _require(
        _mapping(
            resource["evidence"],
            "config.resource_ledger.full3d.evidence",
        )["status"]
        == resource["status"],
        "Full3D resource and evidence statuses differ",
    )
    if resource["status"] != "completed" or not pointer_complete:
        return False, False
    target = _mapping(expected["full3d_resource"], "expected.full3d_resource")
    structural = (
        _integer(resource["active_rows"], "full3d.active_rows")
        < target["active_rows_max_exclusive"]
        and _integer(resource["matrix_nnz"], "full3d.matrix_nnz")
        < target["matrix_nnz_max_exclusive"]
        and _integer(resource["factor_nnz"], "full3d.factor_nnz")
        < target["factor_nnz_max_exclusive"]
        and resource["same_mpi_solver_lifecycle_telemetry"] is True
        and _finite(resource["swap_gib"], "full3d.swap_gib")
        <= target["swap_gib_max"]
    )
    peak = _finite(
        resource["solver_phase_peak_gib"],
        "full3d.solver_phase_peak_gib",
    )
    return (
        structural and peak <= target["solver_phase_peak_mandatory_gib"],
        structural and peak <= target["solver_phase_peak_preferred_gib"],
    )


def _validate_hybrid(
    config: Mapping[str, Any],
    expected: Mapping[str, Any],
    case_dir: Path,
    source_sha: str | None,
    hidden_pass: bool,
) -> tuple[bool, bool]:
    hybrid = _mapping(config["hybrid"], "config.hybrid")
    target = _mapping(expected["hybrid"], "expected.hybrid")
    _require(
        hybrid["mode_count"] == target["initial_mode_count"] == 120,
        "initial Hybrid gate must use M120",
    )
    raw_names = (
        "same_frozen_hp_space",
        "power_pass_count",
        "complex_amplitude_pass_count",
        "total_observables_pass",
        "field_observables_pass",
        "residual_pass",
    )
    if hybrid["status"] == "not_run":
        _require(
            all(hybrid[name] is None for name in raw_names),
            "not_run Hybrid gate contains result claims",
        )
    hybrid_evidence = _validate_pointer(
        hybrid["evidence"],
        case_dir,
        source_sha,
        "config.hybrid.evidence",
        role="hybrid_gate",
    )
    _require(
        _mapping(hybrid["evidence"], "config.hybrid.evidence")["status"]
        == hybrid["status"],
        "Hybrid gate and evidence statuses differ",
    )
    gate_pass = (
        hybrid["status"] == "completed"
        and hybrid_evidence
        and hidden_pass
        and hybrid["same_frozen_hp_space"] is True
        and hybrid["power_pass_count"] == target["power_pass_required"]
        and hybrid["complex_amplitude_pass_count"]
        == target["complex_amplitude_pass_required"]
        and hybrid["total_observables_pass"] is True
        and hybrid["field_observables_pass"] is True
        and hybrid["residual_pass"] is True
    )

    resource = _mapping(
        _mapping(config["resource_ledger"], "config.resource_ledger")["hybrid"],
        "config.resource_ledger.hybrid",
    )
    resource_names = (
        "active_rows_below_baseline",
        "matrix_nnz_below_baseline",
        "factor_nnz_below_baseline",
        "solver_phase_peak_gib",
        "swap_gib",
        "same_mpi_solver_lifecycle_telemetry",
    )
    if resource["status"] == "not_run":
        _require(
            all(resource[name] is None for name in resource_names),
            "not_run Hybrid resource ledger contains measurements",
        )
    resource_evidence = _validate_pointer(
        resource["evidence"],
        case_dir,
        source_sha,
        "config.resource_ledger.hybrid.evidence",
        role="hybrid_resource",
    )
    _require(
        _mapping(
            resource["evidence"],
            "config.resource_ledger.hybrid.evidence",
        )["status"]
        == resource["status"],
        "Hybrid resource and evidence statuses differ",
    )
    _require(
        resource["status"] != "completed"
        or (hybrid["status"] == "completed" and hidden_pass),
        "Hybrid resource completion preceded the hidden-audit/Hybrid gate",
    )
    if resource["status"] != "completed" or not resource_evidence:
        return False, False
    structural = (
        resource["active_rows_below_baseline"] is True
        and resource["matrix_nnz_below_baseline"] is True
        and resource["factor_nnz_below_baseline"] is True
        and resource["same_mpi_solver_lifecycle_telemetry"] is True
        and _finite(resource["swap_gib"], "hybrid_resource.swap_gib")
        <= target["swap_gib_max"]
    )
    peak = _finite(
        resource["solver_phase_peak_gib"],
        "hybrid_resource.solver_phase_peak_gib",
    )
    mandatory = (
        gate_pass
        and structural
        and peak < target["solver_phase_peak_baseline_gib"]
    )
    preferred = (
        gate_pass
        and structural
        and peak <= target["solver_phase_peak_preferred_gib"]
    )
    return mandatory, preferred


def check_case098(case_dir: Path | str = CASE098) -> dict[str, Any]:
    """Validate Case098 and recompute every campaign/completion classification."""
    case_dir = Path(case_dir).resolve()
    schema = _load_json(case_dir / "schema.json", "Case098 schema")
    config = _load_json(case_dir / "config.json", "Case098 config")
    expected = _load_json(case_dir / "expected.json", "Case098 expected")
    _validate_schema_is_closed(schema)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(config)
    except Exception as error:
        raise Task035eCase098EvidenceError(
            f"Case098 strict schema validation failed: {error}",
        ) from error
    _validate_expected(expected)

    _require(
        config["formal_mpi_size"] == expected["formal_mpi_size"] == 8,
        "formal Case098 campaign must use MPI8",
    )
    _require(
        config["ordinary_default_changed"]
        is expected["ordinary_default_changed"]
        is False,
        "ordinary default must remain unchanged",
    )
    source_sha = config["source_commit_sha"]
    layer_pass = _validate_layer_packages(config, case_dir, source_sha)
    isolation_pass = _validate_reference_isolation(
        config,
        case_dir,
        source_sha,
    )
    reference_pass, reference_runs = _validate_reference_campaign(
        config,
        expected,
        case_dir,
        source_sha,
    )
    _validate_goal_contract(config, expected)
    _validate_adaptive_contract(config, expected)
    blind_pass, path_pass = _validate_blind_trials(
        config,
        expected,
        case_dir,
        source_sha,
    )
    freeze_pass = _validate_freeze(config, source_sha)
    hidden_pass = _validate_hidden_audit(
        config,
        expected,
        case_dir,
        source_sha,
        freeze_pass,
    )
    full3d_pass, full3d_preferred = _validate_full3d_resource(
        config,
        expected,
        case_dir,
        source_sha,
    )
    hybrid_pass, hybrid_preferred = _validate_hybrid(
        config,
        expected,
        case_dir,
        source_sha,
        hidden_pass,
    )

    completion_pass = (
        reference_pass
        and blind_pass
        and freeze_pass
        and hidden_pass
        and full3d_pass
        and isolation_pass
        and all(layer_pass.values())
    )
    _require(
        config["numerical_credit_claimed"] is completion_pass,
        "numerical_credit_claimed differs from recomputed formal gates",
    )
    campaign_status = config["campaign_status"]
    _require(
        (campaign_status == "completed") is completion_pass,
        "campaign_status completed differs from recomputed formal gates",
    )
    all_not_run = (
        all(
            run["status"] == "not_run"
            for run in config["reference_campaign"]["runs"]
        )
        and all(path["status"] == "not_run" for path in config["blind_trials"]["paths"])
        and config["reference_campaign"]["convergence_authority"]["status"]
        == "not_run"
        and config["blind_trials"]["two_start_comparison"]["evidence"]["status"]
        == "not_run"
        and config["freeze"]["status"] == "not_run"
        and config["hidden_audit"]["status"] == "not_run"
        and config["resource_ledger"]["full3d"]["status"] == "not_run"
        and config["resource_ledger"]["hybrid"]["status"] == "not_run"
        and config["hybrid"]["status"] == "not_run"
        and all(
            layer["package_manifest"]["status"] == "not_run"
            for layer in config["layer_packages"].values()
        )
        and config["reference_isolation"]["status"] == "not_run"
        and source_sha is None
    )
    _require(
        (campaign_status == "scaffold_not_run") is all_not_run,
        "scaffold_not_run status differs from raw execution states",
    )
    if all_not_run:
        classification = "SCAFFOLD_NOT_RUN"
    elif completion_pass and hybrid_pass:
        classification = "SUCCESS_REFERENCE_BLIND_HP_AND_HYBRID"
    elif completion_pass:
        classification = "SUCCESS_REFERENCE_BLIND_HP"
    elif any(
        run["run_id"] == "p6_h5"
        and run["status"] == "controlled_resource_stop"
        for run in config["reference_campaign"]["runs"]
    ):
        classification = "REFERENCE_CERTIFICATION_INCOMPLETE"
    else:
        classification = "PARTIAL_WITH_CONTROLLED_NEGATIVES"

    if all_not_run:
        _require(
            classification == expected["initial_classification"]
            and completion_pass is expected["initial_completion_pass"]
            and config["numerical_credit_claimed"]
            is expected["initial_numerical_credit"],
            "initial scaffold classification differs from expected contract",
        )

    return {
        "schema_version": "task035e.case098-check.v1",
        "case_id": config["case_id"],
        "evidence_valid": True,
        "classification": classification,
        "completion_pass": completion_pass,
        "hybrid_pass": hybrid_pass,
        "reference_qualified": reference_pass,
        "reference_run_gate_pass": reference_runs,
        "layer_package_pass": layer_pass,
        "reference_isolation_pass": isolation_pass,
        "blind_path_pass": path_pass,
        "freeze_pass": freeze_pass,
        "hidden_audit_pass": hidden_pass,
        "full3d_resource_mandatory_pass": full3d_pass,
        "full3d_resource_preferred_pass": full3d_preferred,
        "hybrid_resource_mandatory_pass": hybrid_pass,
        "hybrid_resource_preferred_pass": hybrid_preferred,
        "ordinary_default_changed": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, default=CASE098)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = check_case098(args.case_dir)
    except Task035eCase098EvidenceError as error:
        report = {
            "schema_version": "task035e.case098-check.v1",
            "evidence_valid": False,
            "completion_pass": False,
            "error": str(error),
        }
        exit_code = 2
    else:
        exit_code = int(args.require_complete and not report["completion_pass"])
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
