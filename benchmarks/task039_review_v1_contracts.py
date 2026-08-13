"""Pure Review V1 contracts for the finite Task39 extension."""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task039_full3d_identity import _load_run
from benchmarks.task037c_robustness import profile_record
from src.io.resolved_config import canonical_json_bytes
from src.runners.task039_hybrid_iterative import (
    _RESIDUAL_KEYS,
    make_task039_hybrid_iterative_profile,
    task039_hybrid_iterative_authority_errors,
)

TASK039_GRID_TARGETS = (7.5, 6.0, 5.0)
TASK039_M480_PROGRESS_ROWS = (0, 20, 60, 100, 200, 500, 1000, 2000, 4000, 6000)
TASK039_GRID_SIGNIFICANCE_FLOOR = 1.0e-8
TASK039_M480_RESIDUAL_LIMIT = 5.0e-9


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is not a finite scalar")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _array(value: Any, label: str) -> np.ndarray:
    result = np.asarray(value)
    if not np.isfinite(result).all():
        raise ValueError(f"{label} contains non-finite values")
    return result


def _relative(left: float, right: float, floor: float = 1.0e-15) -> tuple[float, float]:
    denominator = max(abs(left), abs(right), floor)
    return abs(left - right) / denominator, denominator


def _complex_relative(left: complex, right: complex) -> tuple[float, float]:
    denominator = max(abs(left), abs(right), 1.0e-15)
    return abs(left - right) / denominator, denominator


def _mode_key(item: Any) -> tuple[str, int, int, str]:
    if isinstance(item, Mapping):
        return (
            str(item["side"]),
            int(item["m"]),
            int(item["n"]),
            str(item["polarization"]),
        )
    if isinstance(item, (list, tuple)) and len(item) == 4:
        return str(item[0]), int(item[1]), int(item[2]), str(item[3])
    raise ValueError(f"invalid Task39 mode key: {item!r}")


def _mode_keys(value: Any) -> set[tuple[str, int, int, str]]:
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("mode keys are not a sequence")
    keys = {_mode_key(item) for item in value}
    if len(keys) != len(value):
        raise ValueError("mode keys are not unique")
    return keys


def _resolved_physics_identity(
    resolved: Mapping[str, Any], inventory: Mapping[str, Any]
) -> dict[str, Any]:
    for name in ("geometry", "materials", "incidence", "boundary", "method", "solver"):
        if not isinstance(resolved.get(name), Mapping):
            raise ValueError(f"resolved {name} identity is missing")
    discretization = resolved.get("discretization")
    if not isinstance(discretization, Mapping):
        raise ValueError("resolved discretization identity is missing")
    keys = inventory.get("keys")
    key_sha256 = inventory.get("key_sha256", inventory.get("canonical_sha256"))
    if key_sha256 is None and isinstance(keys, list):
        key_sha256 = _identity_sha256([list(_mode_key(item)) for item in keys])
    return {
        "geometry": resolved.get("geometry"),
        "materials": resolved.get("materials"),
        "incidence": resolved.get("incidence"),
        "boundary": resolved.get("boundary"),
        "method": resolved.get("method"),
        "solver": resolved.get("solver"),
        "discretization": {
            key: value
            for key, value in discretization.items()
            if key != "mesh_target_nm"
        },
        "external_mode_inventory": {
            "count": inventory.get("count", len(inventory.get("keys", []))),
            "key_sha256": key_sha256 or "not_available",
        },
    }


def _resolved_equation_identity(
    resolved: Mapping[str, Any], inventory: Mapping[str, Any]
) -> dict[str, Any]:
    """Identify the equation/discretization while allowing method/solver changes."""

    for name in ("geometry", "materials", "incidence", "boundary"):
        if not isinstance(resolved.get(name), Mapping):
            raise ValueError(f"resolved {name} identity is missing")
    discretization = resolved.get("discretization")
    if not isinstance(discretization, Mapping):
        raise ValueError("resolved discretization identity is missing")
    method = resolved.get("method")
    if not isinstance(method, Mapping):
        raise ValueError("resolved method identity is missing")
    keys = inventory.get("keys")
    key_sha256 = inventory.get("key_sha256", inventory.get("canonical_sha256"))
    if key_sha256 is None and isinstance(keys, list):
        key_sha256 = _identity_sha256([list(_mode_key(item)) for item in keys])
    return {
        "geometry": resolved["geometry"],
        "materials": resolved["materials"],
        "incidence": resolved["incidence"],
        "boundary": resolved["boundary"],
        "discretization": dict(discretization),
        "method_equation": {
            key: value for key, value in method.items() if key != "kind"
        },
        "external_mode_inventory": {
            "count": inventory.get("count", len(inventory.get("keys", []))),
            "key_sha256": key_sha256 or "not_available",
        },
    }


def _identity_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def mesh_resource_preflight(
    mesh_target_nm: float,
    *,
    selected_limit_gib: float,
    predicted_peak_gib: float | None = None,
    swap_mib: float = 0.0,
    capacity_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the finite mesh/resource decision without estimating a mesh."""
    mesh = _number(mesh_target_nm, "mesh_target_nm")
    if mesh not in (7.5, 6.0, 5.0):
        raise ValueError("Review V1 mesh preflight accepts h7.5, h6, or h5")
    selected = _number(selected_limit_gib, "selected_limit_gib")
    swap = _number(swap_mib, "swap_mib")
    effective_hard = min(195.0, 0.90 * selected)
    snapshot = capacity_snapshot if isinstance(capacity_snapshot, Mapping) else {}

    def gate(
        name: str, passed: bool, value: Any, reason: str, classification: str
    ) -> dict[str, Any]:
        return {
            "name": name,
            "value": value,
            "classification": classification,
            "status": "pass" if passed else "not_ready",
            "pass": bool(passed),
            "reason": reason,
        }

    peak_range = snapshot.get("predicted_process_tree_peak_range_gib")
    range_valid = (
        isinstance(peak_range, (list, tuple))
        and len(peak_range) == 2
        and all(_finite(value) for value in peak_range)
        and float(peak_range[0]) <= float(peak_range[1])
    )
    upper_peak = float(peak_range[1]) if range_valid else None
    explicit_matches = predicted_peak_gib is None or (
        range_valid
        and _finite(predicted_peak_gib)
        and float(predicted_peak_gib) == upper_peak
    )
    threshold = min(effective_hard, 180.0) if mesh == 5.0 else effective_hard
    prediction_pass = range_valid and explicit_matches and upper_peak <= threshold
    prediction = {
        "status": "predicted" if range_valid else "not_established",
        "classification": "derived" if range_valid else "not_available",
        "range_gib": list(peak_range) if range_valid else "not_available",
        "upper_bound_gib": upper_peak if upper_peak is not None else "not_available",
        "explicit_peak_gib": predicted_peak_gib
        if predicted_peak_gib is not None
        else "not_provided",
        "explicit_matches_upper": explicit_matches,
        "threshold_gib": threshold,
        "pass": prediction_pass,
        "reason": "range upper bound is the sole formal prediction source",
    }
    capacity_fields = (
        "cells",
        "full_fe_dofs",
        "active_trace_rows",
        "assembled_rows",
        "assembled_nnz_estimate",
        "dynamic_inventory_count",
        "dynamic_inventory_keys_exact",
        "predicted_factor_nnz",
        "predicted_process_tree_peak_range_gib",
        "available_memory_gib",
        "disk_free_gib",
        "disk_required_gib",
    )
    present = {
        key: key in snapshot and snapshot[key] not in (None, "not_available")
        for key in capacity_fields
    }
    numeric_capacity = all(
        key in snapshot and _finite(snapshot[key]) and float(snapshot[key]) >= 0.0
        for key in capacity_fields
        if key
        not in {"dynamic_inventory_keys_exact", "predicted_process_tree_peak_range_gib"}
    )
    capacity_pass = (
        all(present.values())
        and numeric_capacity
        and range_valid
        and snapshot.get("dynamic_inventory_count") == 604
        and snapshot.get("dynamic_inventory_keys_exact") is True
    )
    symbolic = snapshot.get("symbolic_status", "not_available")
    analysis = snapshot.get("analysis_status", "not_available")
    both_unavailable = symbolic == "not_available" and analysis == "not_available"
    symbolic_available_pass = symbolic == "pass" and analysis == "pass"
    symbolic_available_fail = symbolic not in {
        "pass",
        "not_available",
    } or analysis not in {"pass", "not_available"}
    symbolic_pass = symbolic_available_pass or (both_unavailable and mesh != 5.0)
    symbolic_class = "measured" if symbolic_available_pass else "not_available"
    symbolic_status = (
        "pass"
        if symbolic_available_pass
        else (
            "nonblocking_not_available"
            if both_unavailable and mesh != 5.0
            else "not_ready"
        )
    )
    disk_free = snapshot.get("disk_free_gib")
    disk_required = snapshot.get("disk_required_gib")
    disk_capacity_pass = (
        _finite(disk_free)
        and _finite(disk_required)
        and float(disk_free) >= float(disk_required)
    )
    disk_reported = snapshot.get("disk_sufficient")
    disk_inputs_finite = _finite(disk_free) and _finite(disk_required)
    disk_consistent = disk_reported is None or disk_reported is disk_capacity_pass
    evidence = {
        "input_identity": gate(
            "input_identity",
            snapshot.get("input_identity_exact") is True,
            snapshot.get("input_identity_exact", "not_available"),
            "hash-bound input identity is required",
            "measured",
        ),
        "capacity_snapshot": gate(
            "capacity_snapshot",
            snapshot.get("capacity_snapshot_status") == "available",
            snapshot.get("capacity_snapshot_status", "not_available"),
            "named capacity snapshot is required",
            "measured",
        ),
        "capacity_fields": gate(
            "capacity_fields",
            capacity_pass,
            present,
            "named rows, NNZ, inventory, peak, memory and disk fields are required",
            "mixed_measured_derived" if capacity_pass else "not_established",
        ),
        "selected_limit_finite": gate(
            "selected_limit_finite",
            isfinite(selected),
            selected,
            "selected finite memory limit",
            "measured",
        ),
        "predicted_peak": gate(
            "predicted_peak",
            prediction_pass,
            prediction,
            "predicted range upper bound must be below the mesh limit",
            "derived" if range_valid else "not_available",
        ),
        "symbolic_analysis": {
            "value": {"symbolic": symbolic, "analysis": analysis},
            "classification": symbolic_class,
            "status": symbolic_status,
            "pass": symbolic_pass,
            "reason": "unavailable is nonblocking for h7.5/h6; h5 requires both pass"
            if both_unavailable
            else "available failures block",
        },
        "disk_sufficient": gate(
            "disk_sufficient",
            disk_capacity_pass and disk_consistent,
            {
                "free_gib": disk_free,
                "required_gib": disk_required,
                "reported": disk_reported,
                "recomputed": disk_capacity_pass,
            },
            "disk_free_gib >= disk_required_gib is recomputed and reported bool is cross-checked",
            "measured" if disk_inputs_finite else "not_available",
        ),
        "swap_zero": gate(
            "swap_zero",
            swap == 0.0,
            swap,
            "any swap use blocks the mesh gate",
            "measured",
        ),
    }
    mesh_pass = (
        all(item["pass"] for item in evidence.values()) and not symbolic_available_fail
    )
    if mesh == 5.0:
        factor = snapshot.get("factor_bytes")
        workspace = snapshot.get("workspace_bytes")
        hard_bytes = effective_hard * 1024.0**3
        bytes_valid = (
            _finite(factor)
            and _finite(workspace)
            and float(factor) > 0.0
            and float(workspace) > 0.0
        )
        margin = (
            (hard_bytes - float(factor) - float(workspace)) / hard_bytes
            if bytes_valid
            else None
        )
        measured = {
            key: snapshot.get(key) is True
            for key in ("h10_measured", "h7p5_measured", "h6_measured")
        }
        h5_extra = {
            "status": "ready"
            if all(measured.values())
            and mesh_pass
            and prediction.get("upper_bound_gib", float("inf")) <= 180.0
            and symbolic_available_pass
            and margin is not None
            and margin >= 0.15
            else "not_ready",
            "h10_measured": measured["h10_measured"],
            "h7p5_measured": measured["h7p5_measured"],
            "h6_measured": measured["h6_measured"],
            "symbolic_analysis_pass": symbolic_available_pass,
            "factor_workspace_margin": {
                "factor_bytes": factor,
                "workspace_bytes": workspace,
                "margin": margin,
                "threshold": 0.15,
                "pass": margin is not None and margin >= 0.15,
                "classification": "derived" if margin is not None else "not_available",
            },
            "predicted_peak_below_180": prediction.get(
                "upper_bound_gib", "not_available"
            )
            != "not_available"
            and prediction["upper_bound_gib"] <= 180.0,
        }
        h5_extra["pass"] = h5_extra["status"] == "ready"
    else:
        h5_extra = {"status": "not_applicable", "pass": True}
    all_pass = mesh_pass and h5_extra["pass"]
    return {
        "mesh_target_nm": mesh,
        "warning_gib": 170.0,
        "configured_hard_gib": 195.0,
        "selected_limit_gib": selected,
        "effective_hard_gib": effective_hard,
        "effective_hard_formula": "min(195 GiB, 0.90*selected finite limit)",
        "swap_mib": swap,
        "swap_pass": swap == 0.0,
        "mesh_gate": {
            "status": "ready" if mesh_pass else "not_ready",
            "pass": mesh_pass,
            "prediction": prediction,
            "base_evidence": evidence,
        },
        "h5_extra_gate": h5_extra,
        "evidence": evidence,
        "all_pass": all_pass,
        "classification": "preflight_pass" if all_pass else "not_established",
    }


def load_full3d_grid_view(
    run_directory: str | Path, mesh_target_nm: float
) -> dict[str, Any]:
    """Load one direct raw run through the accepted Full3D identity loader."""

    raw = _load_run(
        run_directory,
        "direct",
        expected_mesh_target_size=float(mesh_target_nm),
    )
    root = Path(raw["root"])
    manifest = raw["manifest"]
    resolved_path = root / "resolved_config.json"
    resolved_bytes = resolved_path.read_bytes()
    resolved_sha256 = hashlib.sha256(resolved_bytes).hexdigest()
    if resolved_sha256 != manifest.get("resolved_config_sha256"):
        raise ValueError("resolved_config.json hash does not match manifest")
    resolved = json.loads(resolved_bytes)
    if not isinstance(resolved, Mapping):
        raise ValueError("resolved_config.json is not an object")
    resolved_identity = _resolved_physics_identity(resolved, raw["inventory"])
    equation_identity = _resolved_equation_identity(resolved, raw["inventory"])
    numeric = raw["numeric"]
    if "A_volume" in numeric:
        a_volume = numeric["A_volume"]
    else:
        a_volume = numeric["A_volume_total"]
    observables = {
        "R_total": _number(numeric["R_total"], "R_total"),
        "T_total": _number(numeric["T_total"], "T_total"),
        "A_balance": _number(numeric["A_balance"], "A_balance"),
        "A_volume": _number(a_volume, "A_volume"),
    }
    physics_except_mesh_sha256 = _identity_sha256(resolved_identity)
    return {
        "mesh_target_nm": float(mesh_target_nm),
        "physical_model_sha256": raw["manifest"]["physical_model_sha256"],
        "physics_except_mesh_identity": resolved_identity,
        "physics_except_mesh_sha256": physics_except_mesh_sha256,
        "resolved_config_path": str(resolved_path),
        "resolved_config_sha256": resolved_sha256,
        "resolved_physics_identity": resolved_identity,
        "resolved_physics_identity_sha256": physics_except_mesh_sha256,
        "equation_identity": equation_identity,
        "equation_identity_sha256": _identity_sha256(equation_identity),
        "method_solver_identity": {
            "method": resolved["method"],
            "solver": resolved["solver"],
        },
        "inventory_identity": resolved_identity["external_mode_inventory"],
        "mode_keys": list(raw["inventory"]["keys"]),
        "orders": raw["orders"]["rows"],
        "observables": observables,
        "closure": _number(
            numeric["energy_closure_error_port_volume"], "energy closure"
        ),
        "coordinates": raw["reference"]["coordinates"],
        "fields": {
            "E_V_per_m": raw["reference"]["arrays"]["E_V_per_m"],
            "H_A_per_m": raw["reference"]["arrays"]["H_A_per_m"],
        },
        "source": str(root),
    }


def _scalar_gate(
    left: float,
    right: float,
    *,
    mandatory: float,
    strong: float,
) -> dict[str, Any]:
    delta, denominator = _relative(left, right)
    return {
        "left": left,
        "right": right,
        "actual": {"left": left, "right": right},
        "abs_delta": abs(left - right),
        "relative_delta": delta,
        "denominator": denominator,
        "mandatory_threshold": mandatory,
        "strong_threshold": strong,
        "mandatory_pass": abs(left - right) <= mandatory,
        "strong_pass": abs(left - right) <= strong,
        "mandatory_status": "pass" if abs(left - right) <= mandatory else "fail",
        "strong_status": "pass" if abs(left - right) <= strong else "fail",
    }


def _field_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    if left.shape != right.shape or left.ndim != 4 or left.shape[-1] != 3:
        raise ValueError("field arrays must have equal shape (planes, y, x, 3)")
    difference = left - right
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    absolute_l2 = float(np.linalg.norm(difference))
    denominator = max(left_norm, right_norm, 1.0e-30)
    plane = [
        {
            "reference_norm": float(np.linalg.norm(left[index])),
            "candidate_norm": float(np.linalg.norm(right[index])),
            "absolute_l2": float(np.linalg.norm(difference[index])),
            "relative_l2": float(
                np.linalg.norm(difference[index])
                / max(
                    float(np.linalg.norm(left[index])),
                    float(np.linalg.norm(right[index])),
                    1.0e-30,
                )
            ),
            "max_abs": float(np.max(np.abs(difference[index]))),
        }
        for index in range(left.shape[0])
    ]
    return {
        "shape": list(left.shape),
        "reference_norm": left_norm,
        "candidate_norm": right_norm,
        "absolute_l2": absolute_l2,
        "denominator": denominator,
        "relative_l2": absolute_l2 / denominator,
        "plane_metrics": plane,
    }


def compare_full3d_grid_views(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    observable_limit: float = 1.0e-4,
    observable_strong_limit: float = 1.0e-5,
    order_mandatory_limit: float = 1.0e-3,
    order_strong_limit: float = 1.0e-4,
    field_limits: Mapping[str, tuple[float, float]] | None = None,
    require_physical_model_exact: bool = False,
    identity_contract: str = "full3d_grid",
) -> dict[str, Any]:
    """Compare two direct grid views without comparing canonical DoF vectors."""

    errors: list[str] = []
    left_physical = left.get("physical_model_sha256")
    right_physical = right.get("physical_model_sha256")
    physical_exact = left_physical == right_physical
    left_physics_identity = left.get(
        "physics_except_mesh_sha256", left.get("physics_except_mesh_identity")
    )
    right_physics_identity = right.get(
        "physics_except_mesh_sha256", right.get("physics_except_mesh_identity")
    )
    physics_except_mesh_exact = (
        left_physics_identity is not None
        and right_physics_identity is not None
        and left_physics_identity == right_physics_identity
    )
    left_resolved_identity = left.get("resolved_physics_identity_sha256")
    right_resolved_identity = right.get("resolved_physics_identity_sha256")
    resolved_identity_exact = (
        left_resolved_identity is not None
        and right_resolved_identity is not None
        and left_resolved_identity == right_resolved_identity
    )
    equation_left_mapping = left.get("equation_identity")
    equation_right_mapping = right.get("equation_identity")
    equation_left = (
        _identity_sha256(equation_left_mapping)
        if isinstance(equation_left_mapping, Mapping)
        else None
    )
    equation_right = (
        _identity_sha256(equation_right_mapping)
        if isinstance(equation_right_mapping, Mapping)
        else None
    )
    equation_hashes_valid = (
        equation_left is not None
        and equation_right is not None
        and left.get("equation_identity_sha256") == equation_left
        and right.get("equation_identity_sha256") == equation_right
    )
    equation_identity_exact = equation_hashes_valid and equation_left == equation_right

    def _m480_equation_identity(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        method = value.get("method_equation")
        return (
            isinstance(method, Mapping)
            and all(
                method.get(key) not in (None, "not_applicable")
                for key in (
                    "bottom_interface_nm",
                    "top_interface_nm",
                    "requested_modes_per_direction",
                    "propagation_model",
                    "traction_model",
                )
            )
            and method.get("requested_modes_per_direction") == 480
        )

    equation_contract_valid = _m480_equation_identity(
        equation_left_mapping
    ) and _m480_equation_identity(equation_right_mapping)
    method_solver_left = left.get("method_solver_identity", "not_available")
    method_solver_right = right.get("method_solver_identity", "not_available")
    method_solver_exact = method_solver_left == method_solver_right
    if identity_contract == "full3d_grid":
        identity_pass = (
            physics_except_mesh_exact
            and resolved_identity_exact
            and (not require_physical_model_exact or physical_exact)
        )
    elif identity_contract == "same_equation":
        left_kind = (
            method_solver_left.get("method", {}).get("kind")
            if isinstance(method_solver_left, Mapping)
            and isinstance(method_solver_left.get("method"), Mapping)
            else None
        )
        right_kind = (
            method_solver_right.get("method", {}).get("kind")
            if isinstance(method_solver_right, Mapping)
            and isinstance(method_solver_right.get("method"), Mapping)
            else None
        )
        roles_valid = {left_kind, right_kind} == {
            "hybrid_iterative",
            "hybrid_direct",
        }
        identity_pass = (
            physical_exact
            and equation_identity_exact
            and equation_hashes_valid
            and equation_contract_valid
            and roles_valid
        )
    else:
        raise ValueError(f"unknown Task39 identity contract: {identity_contract}")
    if not identity_pass:
        errors.append("resolved physics/model identity gate failed")
    left_keys, right_keys = (
        _mode_keys(left["mode_keys"]),
        _mode_keys(right["mode_keys"]),
    )
    keys_exact = len(left_keys) == len(right_keys) == 604 and left_keys == right_keys
    if not keys_exact:
        errors.append("604 external mode keys are not exact")

    observables: dict[str, Any] = {}
    for name in ("R_total", "T_total", "A_balance", "A_volume"):
        observables[name] = _scalar_gate(
            _number(left["observables"][name], f"left {name}"),
            _number(right["observables"][name], f"right {name}"),
            mandatory=observable_limit,
            strong=observable_strong_limit,
        )
        if not observables[name]["mandatory_pass"]:
            errors.append(f"{name} mandatory grid gate failed")
    closure_left = _number(left["closure"], "left closure")
    closure_right = _number(right["closure"], "right closure")
    closure = {
        "left": closure_left,
        "right": closure_right,
        "threshold": 1.0e-5,
        "left_pass": abs(closure_left) <= 1.0e-5,
        "right_pass": abs(closure_right) <= 1.0e-5,
        "left_status": "pass" if abs(closure_left) <= 1.0e-5 else "fail",
        "right_status": "pass" if abs(closure_right) <= 1.0e-5 else "fail",
        "pairwise_abs_delta": abs(closure_left - closure_right),
    }
    if not closure["left_pass"] or not closure["right_pass"]:
        errors.append("energy closure mandatory gate failed")

    significant_rows: list[dict[str, Any]] = []
    max_power = 0.0
    max_amplitude = 0.0
    significant: set[tuple[str, int, int, str]] = set()
    if keys_exact:
        for key in left_keys:
            lrow, rrow = left["orders"][key], right["orders"][key]
            if (
                max(float(lrow["power_ratio"]), float(rrow["power_ratio"]))
                >= TASK039_GRID_SIGNIFICANCE_FLOOR
            ):
                significant.add(key)
                power, power_denominator = _relative(
                    float(lrow["power_ratio"]), float(rrow["power_ratio"])
                )
                amplitude, amplitude_denominator = _complex_relative(
                    complex(lrow["outgoing_amplitude"]),
                    complex(rrow["outgoing_amplitude"]),
                )
                max_power, max_amplitude = (
                    max(max_power, power),
                    max(max_amplitude, amplitude),
                )
                result = {
                    "key": list(key),
                    "power_left": float(lrow["power_ratio"]),
                    "power_right": float(rrow["power_ratio"]),
                    "power_relative_delta": power,
                    "power_denominator": power_denominator,
                    "amplitude_left": [
                        float(complex(lrow["outgoing_amplitude"]).real),
                        float(complex(lrow["outgoing_amplitude"]).imag),
                    ],
                    "amplitude_right": [
                        float(complex(rrow["outgoing_amplitude"]).real),
                        float(complex(rrow["outgoing_amplitude"]).imag),
                    ],
                    "amplitude_relative_delta": amplitude,
                    "amplitude_denominator": amplitude_denominator,
                    "mandatory_limit": order_mandatory_limit,
                    "strong_limit": order_strong_limit,
                    "power_mandatory_pass": power <= order_mandatory_limit,
                    "power_strong_pass": power <= order_strong_limit,
                    "amplitude_mandatory_pass": amplitude <= order_mandatory_limit,
                    "amplitude_strong_pass": amplitude <= order_strong_limit,
                    "power_mandatory_status": (
                        "pass" if power <= order_mandatory_limit else "fail"
                    ),
                    "power_strong_status": (
                        "pass" if power <= order_strong_limit else "fail"
                    ),
                    "amplitude_mandatory_status": (
                        "pass" if amplitude <= order_mandatory_limit else "fail"
                    ),
                    "amplitude_strong_status": (
                        "pass" if amplitude <= order_strong_limit else "fail"
                    ),
                    "mandatory_status": (
                        "pass"
                        if power <= order_mandatory_limit
                        and amplitude <= order_mandatory_limit
                        else "fail"
                    ),
                    "strong_status": (
                        "pass"
                        if power <= order_strong_limit
                        and amplitude <= order_strong_limit
                        else "fail"
                    ),
                }
                significant_rows.append(result)
    order_failures = [
        row for row in significant_rows if row["mandatory_status"] != "pass"
    ]
    order_strong_failures = [
        row for row in significant_rows if row["strong_status"] != "pass"
    ]
    if order_failures:
        errors.append("significant diffraction order gate failed")

    coordinates_exact = all(
        np.array_equal(left["coordinates"][name], right["coordinates"][name])
        for name in ("x_nm", "y_nm", "z_nm")
    )
    if not coordinates_exact:
        errors.append("common grid coordinates are not exact")
    fields: dict[str, Any] = {}
    limits = field_limits or {
        "E_V_per_m": (5.0e-3, 2.0e-3),
        "H_A_per_m": (1.0e-2, 5.0e-3),
    }
    for name in ("E_V_per_m", "H_A_per_m"):
        left_field = _array(left["fields"][name], f"left {name}")
        right_field = _array(right["fields"][name], f"right {name}")
        fields[name] = _field_metrics(left_field, right_field)
        threshold, strong_threshold = limits[name]
        fields[name]["mandatory_threshold"] = threshold
        fields[name]["mandatory_pass"] = (
            coordinates_exact and fields[name]["relative_l2"] <= threshold
        )
        fields[name]["mandatory_status"] = (
            "pass" if fields[name]["mandatory_pass"] else "fail"
        )
        fields[name]["strong_threshold"] = strong_threshold
        fields[name]["strong_pass"] = (
            coordinates_exact and fields[name]["relative_l2"] <= strong_threshold
        )
        fields[name]["strong_status"] = (
            "pass" if fields[name]["strong_pass"] else "fail"
        )
        if not fields[name]["mandatory_pass"]:
            errors.append(f"{name} mandatory grid gate failed")
    observables_mandatory = all(item["mandatory_pass"] for item in observables.values())
    observables_strong = all(item["strong_pass"] for item in observables.values())
    closure_mandatory = closure["left_pass"] and closure["right_pass"]
    fields_mandatory = all(item["mandatory_pass"] for item in fields.values())
    fields_strong = all(item["strong_pass"] for item in fields.values())
    mandatory_pass = (
        identity_pass
        and keys_exact
        and observables_mandatory
        and closure_mandatory
        and coordinates_exact
        and fields_mandatory
        and not order_failures
    )
    strong_pass = (
        mandatory_pass
        and observables_strong
        and fields_strong
        and not order_strong_failures
    )
    return {
        "schema": "task039.review-v1.grid-comparison.v1",
        "pass": mandatory_pass,
        "classification": "grid_mandatory_pass"
        if mandatory_pass
        else "grid_mandatory_fail",
        "physical_model_sha256": {
            "left": left_physical,
            "right": right_physical,
        },
        "physical_model_exact": physical_exact,
        "require_physical_model_exact": require_physical_model_exact,
        "identity_contract": identity_contract,
        "resolved_physics_identity_exact": resolved_identity_exact,
        "physics_except_mesh_identity": {
            "left": left_physics_identity,
            "right": right_physics_identity,
        },
        "physics_except_mesh_exact": physics_except_mesh_exact,
        "equation_identity_exact": equation_identity_exact,
        "equation_hashes_valid": equation_hashes_valid,
        "equation_contract_valid": equation_contract_valid,
        "equation_identity": {"left": equation_left, "right": equation_right},
        "method_solver_identity": {
            "left": method_solver_left,
            "right": method_solver_right,
            "exact": method_solver_exact,
            "difference_allowed": identity_contract == "same_equation",
            "same_equation_roles": (
                "hybrid_iterative"
                if identity_contract == "same_equation"
                else "not_applicable",
                "hybrid_direct"
                if identity_contract == "same_equation"
                else "not_applicable",
            ),
        },
        "mode_keys_exact": keys_exact,
        "mode_count": len(left_keys),
        "significant_order_count": len(significant),
        "significant_power_floor": TASK039_GRID_SIGNIFICANCE_FLOOR,
        "max_power_relative_delta": max_power,
        "max_amplitude_relative_delta": max_amplitude,
        "significant_rows": significant_rows,
        "order_failures": order_failures,
        "order_strong_failures": order_strong_failures,
        "order_mandatory_pass": not order_failures,
        "order_strong_pass": not order_strong_failures,
        "mandatory_pass": mandatory_pass,
        "strong_pass": strong_pass,
        "observables_mandatory_pass": observables_mandatory,
        "observables_strong_pass": observables_strong,
        "closure_mandatory_pass": closure_mandatory,
        "fields_mandatory_pass": fields_mandatory,
        "fields_strong_pass": fields_strong,
        "order_limits": {
            "mandatory": order_mandatory_limit,
            "strong": order_strong_limit,
        },
        "observable_limits": {
            "mandatory": observable_limit,
            "strong": observable_strong_limit,
        },
        "observables": observables,
        "closure": closure,
        "coordinates_exact": coordinates_exact,
        "fields": fields,
        "errors": errors,
    }


def check_m480_hybrid_iterative(
    record: Mapping[str, Any],
    direct_reference: Mapping[str, Any],
    *,
    resource_authority: Mapping[str, Any],
    comparison_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Check the solver-only M480 contract and its direct-reference observables."""
    profile_data = record.get("profile")
    inventory = record.get("external_mode_inventory")
    source = record.get("source")
    before = source.get("before") if isinstance(source, Mapping) else None
    profile_errors: list[str] = []
    if (
        not isinstance(profile_data, Mapping)
        or profile_data.get("requested_modes") != 480
    ):
        profile_errors.append("M480 iterative profile is missing or not M480")
        profile = None
    elif profile_data.get("mpi_size") not in (1, 8):
        profile_errors.append("profile.mpi_size must be MPI1 or MPI8")
        profile = None
    else:
        profile = make_task039_hybrid_iterative_profile(
            480, int(profile_data["mpi_size"])
        )
        if profile_record(profile) != dict(profile_data):
            profile_errors.append("M480 iterative profile is not exact")
    if (
        profile is not None
        and isinstance(inventory, Mapping)
        and isinstance(before, Mapping)
    ):
        profile_errors.extend(
            task039_hybrid_iterative_authority_errors(
                record,
                source_sha=str(before.get("commit_sha")),
                profile=profile,
                inventory=inventory,
            )
        )
    else:
        profile_errors.append("M480 shared online authority inputs are missing")
    errors = list(dict.fromkeys(profile_errors))
    linear = record.get("linear")
    iterations = 0
    if not isinstance(linear, Mapping):
        errors.append("linear authority is missing")
    else:
        if not (
            isinstance(linear.get("reason"), int)
            and linear["reason"] > 0
            and isinstance(linear.get("iterations"), int)
            and 0 < linear["iterations"] <= 6000
        ):
            errors.append("linear reason/iterations are invalid")
        iterations = (
            int(linear.get("iterations", 0))
            if isinstance(linear.get("iterations"), int)
            else 0
        )
    history = linear.get("history") if isinstance(linear, Mapping) else None
    observed_rows = history if isinstance(history, (list, tuple)) else []
    history_iterations = [
        row.get("iteration")
        for row in observed_rows
        if isinstance(row, Mapping) and isinstance(row.get("iteration"), int)
    ]
    if len(history_iterations) != len(set(history_iterations)):
        errors.append("M480 linear.history contains duplicate iterations")
    selected_rows = [
        row
        for row in observed_rows
        if isinstance(row, Mapping)
        and isinstance(row.get("iteration"), int)
        and (
            row["iteration"] in TASK039_M480_PROGRESS_ROWS
            or row["iteration"] == iterations
        )
        and row["iteration"] <= iterations
    ]
    observed_progress = tuple(row["iteration"] for row in selected_rows)
    reached = set(observed_progress)
    expected_progress = {row for row in TASK039_M480_PROGRESS_ROWS if row <= iterations}
    if iterations:
        expected_progress.add(iterations)
    if not expected_progress.issubset(reached):
        errors.append(
            "M480 history does not contain all reached frozen checkpoints and terminal row"
        )
    progress_output: list[dict[str, Any]] = []
    for row in selected_rows:
        if not isinstance(row, Mapping):
            errors.append("M480 progress row is not a mapping")
            continue
        if any(
            not _finite(row.get(key)) or float(row[key]) < 0.0 for key in _RESIDUAL_KEYS
        ):
            errors.append("M480 history row lacks five finite nonnegative residuals")
        progress_output.append(
            {
                "iteration": row["iteration"],
                "residuals": {key: row[key] for key in _RESIDUAL_KEYS},
                "diagnostic": row.get(
                    "diagnostic", row.get("diagnostics", "not_available")
                ),
                "pc_apply_count": row.get("pc_apply_count", "not_available"),
                "bottom_action_apply_count": row.get(
                    "bottom_action_apply_count", "not_available"
                ),
                "top_action_apply_count": row.get(
                    "top_action_apply_count", "not_available"
                ),
                "elapsed_seconds": row.get("elapsed_seconds", "not_available"),
            }
        )
    physics = record.get("physics")
    if not isinstance(physics, Mapping):
        errors.append("M480 physics authority is missing")
    else:
        traction = physics.get("traction")
        if not isinstance(traction, Mapping) or any(
            not isinstance(traction.get(side), Mapping)
            or float(traction[side].get("relative_dual", float("inf"))) > 1.0e-8
            for side in ("bottom", "top")
        ):
            errors.append("M480 exact traction gate failed")
        if not all(
            physics.get(key) is True
            for key in ("own_physics_pass", "canonical_pass", "physics_pass")
        ):
            errors.append("M480 own/canonical/physics gates are not true")
        for key in ("interface_continuity", "own_grid", "canonical"):
            if not isinstance(physics.get(key), Mapping):
                errors.append(f"M480 physics.{key} authority is missing")
    recovery = record.get("recovery")
    reports = recovery.get("reports") if isinstance(recovery, Mapping) else None
    if not isinstance(recovery, Mapping) or recovery.get("recovery_pass") is not True:
        errors.append("M480 recovery authority is not passed")
    if not isinstance(reports, Mapping):
        errors.append("M480 recovery reports are missing")
    else:
        for side in ("bottom", "top"):
            report = reports.get(side)
            external_q = (
                report.get("external_q") if isinstance(report, Mapping) else None
            )
            if (
                not isinstance(external_q, Mapping)
                or external_q.get("pass") is not True
                or not _finite(external_q.get("auxiliary_relative_residual"))
                or float(external_q["auxiliary_relative_residual"]) > 1.0e-10
            ):
                errors.append(f"M480 recovery external q {side} exceeds 1e-10")
    resources = resource_authority
    if (
        not isinstance(resources, Mapping)
        or resources.get("status") != "measured"
        or resources.get("zero_swap_observed") is not True
        or resources.get("process_tree_peak_swap_mb") != 0
    ):
        errors.append("M480 outer resource authority does not prove measured zero swap")
    elif (
        isinstance(record.get("profile"), Mapping)
        and record["profile"].get("mpi_size") == 1
    ):
        budget = resources.get("task039_memory_budget")
        if (
            not isinstance(budget, Mapping)
            or not _finite(budget.get("configured_terminate_memory_gib"))
            or not _finite(budget.get("effective_terminate_memory_gib"))
            or float(budget["configured_terminate_memory_gib"]) > 48.0
            or float(budget["effective_terminate_memory_gib"]) > 48.0
        ):
            errors.append("M480 MPI1 configured/effective hard stop must be <=48 GiB")
    inventory = record.get("external_mode_inventory")
    inventory_keys = (
        _mode_keys(inventory.get("keys")) if isinstance(inventory, Mapping) else set()
    )
    observed_order_keys = _mode_keys(
        record.get("physics", {}).get("external_orders", [])
        if isinstance(record.get("physics"), Mapping)
        else []
    )
    if len(inventory_keys) != 604 or observed_order_keys != inventory_keys:
        errors.append("M480 external mode keys are not exact 604")
    comparison = compare_full3d_grid_views(
        comparison_payload,
        direct_reference,
        observable_limit=1.0e-6,
        observable_strong_limit=1.0e-6,
        order_mandatory_limit=1.0e-4,
        order_strong_limit=1.0e-4,
        field_limits={
            "E_V_per_m": (5.0e-3, 5.0e-3),
            "H_A_per_m": (5.0e-3, 5.0e-3),
        },
        require_physical_model_exact=True,
        identity_contract="same_equation",
    )
    if not comparison["pass"]:
        errors.append("M480 direct-reference comparison failed")
    iterative_canonical = comparison_payload.get("canonical")
    direct_canonical = direct_reference.get("canonical")
    canonical = {}
    if not isinstance(iterative_canonical, Mapping) or not isinstance(
        direct_canonical, Mapping
    ):
        errors.append("M480 active/full canonical comparison payload is missing")
    else:
        for role in ("active_trace", "full_fe"):
            left = _array(iterative_canonical[role], f"iterative {role} canonical")
            right = _array(direct_canonical[role], f"direct {role} canonical")
            if left.shape != right.shape:
                errors.append(f"M480 {role} canonical shape differs")
                continue
            absolute = float(np.linalg.norm(left - right))
            denominator = max(
                float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30
            )
            relative = absolute / denominator
            canonical[role] = {
                "absolute_l2": absolute,
                "denominator": denominator,
                "relative_l2": relative,
                "threshold": 1.0e-5,
                "pass": relative <= 1.0e-5,
            }
            if relative > 1.0e-5:
                errors.append(f"M480 {role} canonical gate failed")
    return {
        "schema": "task039.review-v1.m480-hybrid-iterative.v1",
        "pass": not errors,
        "classification": (
            "M480_HYBRID_ITERATIVE_SOLVER_PASS_MODEL_NOT_FULL3D_QUALIFIED"
            if not errors
            else "M480_HYBRID_ITERATIVE_SOLVER_FAIL_AT_5NM"
        ),
        "production_validation_allowed": False,
        "full3d_qualified": False,
        "profile_errors": profile_errors,
        "progress_rows": progress_output,
        "comparison": comparison,
        "canonical": canonical,
        "errors": errors,
    }


def _field_pair(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("E_V_per_m", "H_A_per_m"):
        a, b = (
            _array(left["fields"][name], f"left {name}"),
            _array(right["fields"][name], f"right {name}"),
        )
        metrics = _field_metrics(a, b)
        mandatory_threshold, strong_threshold = (
            (5.0e-3, 2.0e-3) if name == "E_V_per_m" else (1.0e-2, 5.0e-3)
        )
        phase = np.angle(a * np.conj(b))
        metrics["per_plane_component"] = [
            [
                {
                    "reference_norm": float(np.linalg.norm(a[p, ..., c])),
                    "candidate_norm": float(np.linalg.norm(b[p, ..., c])),
                    "absolute_l2": float(np.linalg.norm(a[p, ..., c] - b[p, ..., c])),
                    "denominator": max(
                        float(np.linalg.norm(a[p, ..., c])),
                        float(np.linalg.norm(b[p, ..., c])),
                        1.0e-30,
                    ),
                    "near_zero_denominator": max(
                        float(np.linalg.norm(a[p, ..., c])),
                        float(np.linalg.norm(b[p, ..., c])),
                        1.0e-30,
                    )
                    <= max(1.0e-30, 1.0e-12 * metrics["reference_norm"]),
                    "relative_l2": float(
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                    ),
                    "max_abs": float(np.max(np.abs(a[p, ..., c] - b[p, ..., c]))),
                    "max_phase_error_rad": float(np.max(np.abs(phase[p, ..., c]))),
                    "phase_sensitive_complex_error": float(
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                    ),
                    "mandatory_threshold": mandatory_threshold,
                    "strong_threshold": strong_threshold,
                    "mandatory_pass": bool(
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                        <= mandatory_threshold
                    ),
                    "strong_pass": bool(
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                        <= strong_threshold
                    ),
                    "mandatory_status": "pass"
                    if (
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                        <= mandatory_threshold
                    )
                    else "fail",
                    "strong_status": "pass"
                    if (
                        np.linalg.norm(a[p, ..., c] - b[p, ..., c])
                        / max(
                            float(np.linalg.norm(a[p, ..., c])),
                            float(np.linalg.norm(b[p, ..., c])),
                            1.0e-30,
                        )
                        <= strong_threshold
                    )
                    else "fail",
                }
                for c in range(a.shape[-1])
            ]
            for p in range(a.shape[0])
        ]
        result[name] = metrics
    for name in ("flux", "energy"):
        if name not in left or name not in right:
            result[name] = {
                "supported": False,
                "status": "not_available",
                "mandatory_pass": False,
                "strong_pass": False,
            }
            continue
        left_series, right_series = (
            _array(left[name], f"left {name}"),
            _array(right[name], f"right {name}"),
        )
        if left_series.ndim != 1 or right_series.shape != left_series.shape:
            result[name] = {
                "supported": False,
                "status": "not_available_per_plane",
                "mandatory_pass": False,
                "strong_pass": False,
            }
            continue
        per_plane = [
            _scalar_gate(
                _number(left_series[index], f"left {name}[{index}]"),
                _number(right_series[index], f"right {name}[{index}]"),
                mandatory=1.0e-4,
                strong=1.0e-5,
            )
            for index in range(left_series.size)
        ]
        result[name] = {
            "supported": True,
            "status": "measured_per_plane",
            "per_plane": per_plane,
            "mandatory_pass": all(item["mandatory_pass"] for item in per_plane),
            "strong_pass": all(item["strong_pass"] for item in per_plane),
        }
    return result


def _h_path_coordinates(
    path: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coordinates = path.get("coordinates")
    if not isinstance(coordinates, Mapping):
        raise ValueError("H diagnostic coordinates are missing")
    values = tuple(
        _array(coordinates[name], f"H coordinates {name}")
        for name in ("x_nm", "y_nm", "z_nm")
    )
    z = values[2]
    roles = path.get("plane_roles")
    if len(z) < 7 or not isinstance(roles, (list, tuple)) or len(roles) != len(z):
        raise ValueError("H diagnostic needs five planes plus safe offsets and roles")
    if not {10.0, 30.0, 60.0, 90.0, 110.0}.issubset(set(float(value) for value in z)):
        raise ValueError("H diagnostic misses a frozen reference plane")
    if any(not isinstance(role, str) or not role for role in roles):
        raise ValueError("H diagnostic plane roles are invalid")
    provenance = path.get("offset_provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("source") != "mesh_element_interior"
    ):
        raise ValueError("H safe offsets need mesh-element provenance")
    for side, role in (
        ("bottom", "bottom_element_safe_offset"),
        ("top", "top_element_safe_offset"),
    ):
        evidence = provenance.get(side)
        if not isinstance(evidence, Mapping) or evidence.get("role") != role:
            raise ValueError(f"H {side} safe offset provenance is missing")
        if not isinstance(evidence.get("element_id"), (str, int)):
            raise ValueError(f"H {side} safe offset element identity is missing")
        if not isinstance(evidence.get("distance_from_interface_nm"), (int, float)):
            raise ValueError(f"H {side} safe offset distance is missing")
    return values


def _h_vector_pass(comparison: Mapping[str, Any]) -> bool:
    return (
        comparison["E_V_per_m"]["relative_l2"] <= 5.0e-3
        and comparison["H_A_per_m"]["relative_l2"] <= 1.0e-2
    )


def _h_classification(comparisons: Mapping[str, Any]) -> str:
    native_full = comparisons["native_vs_full3d"]
    curl_full = comparisons["curlE_vs_full3d"]
    native_curl = comparisons["native_vs_curlE"]

    native_full_fail = not _h_vector_pass(native_full)
    curl_full_pass = _h_vector_pass(curl_full)
    native_curl_pass = _h_vector_pass(native_curl)
    if curl_full_pass and native_full_fail:
        return "M480_H_RECOVERY_OR_POSTPROCESS_DEFECT"
    curl_full_fail = not curl_full_pass
    if native_full_fail and curl_full_fail and native_curl_pass:
        return "M480_H_DERIVATIVE_MODAL_TRUNCATION_NOT_CONVERGED"
    vector_pass_native = not native_full_fail
    flux_energy_pass = all(
        comparison.get(metric, {}).get("supported") is True
        and comparison[metric].get("mandatory_pass") is True
        for comparison in comparisons.values()
        for metric in ("flux", "energy")
    )
    component_dominated = any(
        component["relative_l2"] > 1.0e-2
        and component["near_zero_denominator"]
        and component["absolute_l2"] <= 1.0e-12
        for comparison in comparisons.values()
        for plane in comparison["H_A_per_m"]["per_plane_component"]
        for component in plane
    )
    if vector_pass_native and flux_energy_pass and component_dominated:
        return "M480_H_GATE_CONDITIONING_REVIEW_REQUIRED"
    return "M480_H_DISCREPANCY_UNRESOLVED"


def diagnose_h_paths(
    native: Mapping[str, Any],
    curl_e: Mapping[str, Any],
    full3d: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare native/curl-E/Full3D fields at identical physical points."""

    if curl_e.get("curl_source") != "complete_reconstructed_field_analytic_or_fe":
        raise ValueError("curlE must use the complete reconstructed analytic/FE curl")
    paths = {"native": native, "curlE": curl_e, "full3d": full3d}
    coordinates = {label: _h_path_coordinates(path) for label, path in paths.items()}
    coordinates_exact = all(
        np.array_equal(coordinates["native"][index], coordinates[label][index])
        for label in ("curlE", "full3d")
        for index in range(3)
    )
    comparisons = {}
    for left_name, right_name in (
        ("native", "curlE"),
        ("curlE", "full3d"),
        ("native", "full3d"),
    ):
        comparisons[f"{left_name}_vs_{right_name}"] = _field_pair(
            paths[left_name], paths[right_name]
        )
    numeric_gate_pass = coordinates_exact and all(
        comparison["E_V_per_m"]["relative_l2"] <= 5.0e-3
        and comparison["H_A_per_m"]["relative_l2"] <= 1.0e-2
        and all(
            comparison[metric].get("supported") is True
            and comparison[metric].get("mandatory_pass") is True
            for metric in ("flux", "energy")
        )
        for comparison in comparisons.values()
    )
    classification = _h_classification(comparisons)
    classification_evidence = {
        name: {
            field: comparisons[name][field]["relative_l2"]
            for field in ("E_V_per_m", "H_A_per_m")
        }
        for name in (
            "native_vs_full3d",
            "curlE_vs_full3d",
            "native_vs_curlE",
        )
    }
    classification_evidence.update(
        {
            "both_full_comparisons_fail": (
                not _h_vector_pass(comparisons["native_vs_full3d"])
                and not _h_vector_pass(comparisons["curlE_vs_full3d"])
            ),
            "native_vs_curlE_close": _h_vector_pass(comparisons["native_vs_curlE"]),
        }
    )
    diagnostic_complete = coordinates_exact and all(
        comparison[metric].get("supported") is True
        for comparison in comparisons.values()
        for metric in ("flux", "energy")
    )
    return {
        "schema": "task039.review-v1.h-diagnostic.v1",
        "coordinates_exact": coordinates_exact,
        "curl_source": curl_e["curl_source"],
        "z_nm": coordinates["native"][2].tolist(),
        "plane_roles": list(native["plane_roles"]),
        "comparisons": comparisons,
        "classification": classification,
        "classification_evidence": classification_evidence,
        "allowed_classifications": [
            "M480_H_RECOVERY_OR_POSTPROCESS_DEFECT",
            "M480_H_DERIVATIVE_MODAL_TRUNCATION_NOT_CONVERGED",
            "M480_H_GATE_CONDITIONING_REVIEW_REQUIRED",
            "M480_H_DISCREPANCY_UNRESOLVED",
        ],
        "diagnostic_complete": diagnostic_complete,
        "numeric_gate_pass": numeric_gate_pass,
        "pass": numeric_gate_pass,
    }


def audit_m960_trace(
    payload: Mapping[str, Any],
    *,
    evaluate_historical: bool = True,
    historical_modes: tuple[int, ...] = (120, 240, 480),
) -> dict[str, Any]:
    """Recompute the Review V1 infinity-norm trace authority."""

    arrays = {
        name: np.asarray(payload[name], dtype=np.complex128)
        for name in (
            "raw_negative_overlap",
            "canonical_negative_overlap",
            "surface_gram",
            "canonical_mapping",
            "repeat_raw_overlap",
            "repeat_surface_gram",
            "repeat_canonical_mapping",
            "repeat_canonical_negative_overlap",
        )
    }
    raw, canonical = (
        arrays["raw_negative_overlap"],
        arrays["canonical_negative_overlap"],
    )
    gram, mapping = arrays["surface_gram"], arrays["canonical_mapping"]
    repeat_raw = arrays["repeat_raw_overlap"]
    repeat_gram, repeat_mapping = (
        arrays["repeat_surface_gram"],
        arrays["repeat_canonical_mapping"],
    )
    if any(value.shape != raw.shape for value in arrays.values()):
        raise ValueError("M960 trace matrices must have one exact square shape")
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1]:
        raise ValueError("M960 trace matrices must be square")
    if not all(np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("M960 trace matrices contain non-finite values")
    tiny = np.finfo(np.float64).tiny
    dimension = raw.shape[0]
    column_keys = payload.get("column_keys")
    if not isinstance(column_keys, list) or len(column_keys) != dimension:
        raise ValueError("M960 column_keys length must equal matrix dimension")

    def backward_error(
        negative_overlap: np.ndarray, surface: np.ndarray, mapping_: np.ndarray
    ) -> tuple[float, np.ndarray, float]:
        residual = negative_overlap - surface @ mapping_
        denominator = (
            float(np.linalg.norm(negative_overlap, np.inf))
            + float(np.linalg.norm(surface, np.inf))
            * float(np.linalg.norm(mapping_, np.inf))
            + tiny
        )
        return (
            float(np.linalg.norm(residual, np.inf) / denominator),
            residual,
            float(denominator),
        )

    eta, residual, eta_denominator = backward_error(raw, gram, mapping)
    repeat_eta, repeat_residual, repeat_eta_denominator = backward_error(
        repeat_raw, repeat_gram, repeat_mapping
    )
    expected = gram @ mapping
    repeat_expected = repeat_gram @ repeat_mapping

    def forward_error(
        overlap: np.ndarray, expected_overlap: np.ndarray
    ) -> tuple[float, np.ndarray, float]:
        difference = overlap - expected_overlap
        denominator = max(
            float(np.linalg.norm(overlap, np.inf)),
            float(np.linalg.norm(expected_overlap, np.inf)),
            1.0e-30,
        )
        return (
            float(np.linalg.norm(difference, np.inf) / denominator),
            difference,
            float(denominator),
        )

    raw_forward_recomputed, raw_forward_residual, raw_forward_denominator = (
        forward_error(raw, expected)
    )
    representation_recomputed, representation_residual, representation_denominator = (
        forward_error(canonical, expected)
    )
    repeat_raw_forward, repeat_raw_residual, repeat_raw_forward_denominator = (
        forward_error(repeat_raw, repeat_expected)
    )
    (
        repeat_representation,
        repeat_representation_residual,
        repeat_representation_denominator,
    ) = forward_error(arrays["repeat_canonical_negative_overlap"], repeat_expected)
    column_metrics = []
    gram_norm = float(np.linalg.norm(gram, np.inf))
    for index in range(dimension):
        absolute = float(np.linalg.norm(residual[:, index], np.inf))
        denominator = max(
            float(np.linalg.norm(raw[:, index], np.inf)),
            float(np.linalg.norm(expected[:, index], np.inf)),
            1.0e-30,
        )
        column_metrics.append(
            {
                "index": index,
                "key": column_keys[index],
                "absolute": absolute,
                "relative": float(absolute / denominator),
                "denominator": float(denominator),
            }
        )
    worst = max(column_metrics, key=lambda item: item["relative"])

    def matrix_difference(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
        absolute = float(np.linalg.norm(left - right, np.inf))
        denominator = max(
            float(np.linalg.norm(left, np.inf)),
            float(np.linalg.norm(right, np.inf)),
            tiny,
        )
        return {
            "absolute": absolute,
            "denominator": denominator,
            "relative": absolute / denominator,
        }

    repeat_differences = {
        "raw_negative_overlap": matrix_difference(raw, repeat_raw),
        "surface_gram": matrix_difference(gram, repeat_gram),
        "canonical_mapping": matrix_difference(mapping, repeat_mapping),
    }
    historical = payload.get("historical_m_modes")
    historical_entries: dict[str, dict[str, Any]] = {}
    historical_pass = True
    if evaluate_historical and isinstance(historical, Mapping):
        for mode in historical_modes:
            entry = historical.get(mode, historical.get(str(mode)))
            if not isinstance(entry, Mapping):
                historical_pass = False
                historical_entries[str(mode)] = {
                    "status": "not_available",
                    "pass": False,
                }
                continue
            entry_dimension = entry.get("dimension")
            limit = entry.get("dynamic_backward_error_limit")
            eta_value = entry.get("backward_error_eta")
            checks = {
                "raw_forward_error": _finite(entry.get("raw_forward_error"))
                and float(entry["raw_forward_error"]) <= 1.0e-9,
                "backward_error_eta": _finite(eta_value)
                and _finite(limit)
                and float(eta_value) <= float(limit),
                "dimension": isinstance(entry_dimension, int) and entry_dimension > 0,
                "representation_error": _finite(entry.get("representation_error"))
                and float(entry["representation_error"]) <= 1.0e-12,
                "finite": entry.get("finite") is True,
                "sign_order_exact": entry.get("sign_order_exact") is True,
            }
            passed = all(checks.values())
            historical_pass &= passed
            historical_entries[str(mode)] = {
                **dict(entry),
                "checks": checks,
                "pass": passed,
                "status": "pass" if passed else "fail",
            }
    elif evaluate_historical:
        historical_pass = False
    reported_representation_error = payload.get("representation_error", "not_available")
    reported_raw_forward_error = payload.get("raw_forward_error", "not_available")
    dynamic_limit = float(100.0 * np.finfo(np.float64).eps * dimension)
    all_finite = all(
        np.isfinite(value).all()
        for value in (
            residual,
            representation_residual,
            repeat_residual,
            repeat_representation_residual,
            raw_forward_residual,
            repeat_raw_residual,
        )
    )
    condition = float(np.linalg.cond(gram))
    finite = isfinite(condition) and all_finite
    gates = {
        "raw_forward_guard": {
            "value": raw_forward_recomputed,
            "reported": reported_raw_forward_error,
            "threshold": 1.0e-9,
            "pass": raw_forward_recomputed <= 1.0e-9,
        },
        "backward_error_eta": {
            "value": eta,
            "threshold": dynamic_limit,
            "pass": eta <= dynamic_limit,
        },
        "repeat_backward_error_eta": {
            "value": repeat_eta,
            "threshold": dynamic_limit,
            "pass": repeat_eta <= dynamic_limit,
        },
        "representation": {
            "value": representation_recomputed,
            "reported": reported_representation_error,
            "threshold": 1.0e-12,
            "pass": representation_recomputed <= 1.0e-12,
        },
        "column_sign_order_exact": {
            "value": payload.get("column_sign_order_exact"),
            "pass": payload.get("column_sign_order_exact") is True,
        },
        "raw_artifact_exact": {
            "value": payload.get("raw_artifact_exact"),
            "pass": payload.get("raw_artifact_exact") is True,
        },
        "finite_all_trace_arrays": {"value": all_finite, "pass": all_finite},
        "finite_gram_mapping": {"value": finite, "pass": finite},
        "repeat_raw_forward": {
            "value": repeat_raw_forward,
            "threshold": 1.0e-9,
            "pass": repeat_raw_forward <= 1.0e-9,
        },
        "repeat_representation": {
            "value": repeat_representation,
            "threshold": 1.0e-12,
            "pass": repeat_representation <= 1.0e-12,
        },
    }
    if evaluate_historical:
        gates.update(
            {
                "historical_sign_order_exact": {
                    "value": payload.get("historical_sign_order_exact"),
                    "pass": payload.get("historical_sign_order_exact") is True,
                },
                "historical_m120_m240_m480": {
                    "value": historical_entries,
                    "pass": historical_pass,
                },
            }
        )
    passed = all(item["pass"] for item in gates.values())
    return {
        "schema": "task039.review-v1.m960-trace-audit.v1",
        "pass": passed,
        "classification": "M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_PASS"
        if passed
        else "M960_TRACE_AUTHORITY_NUMERICAL_AUDIT_FAIL",
        "dimension": dimension,
        "dynamic_backward_error_limit": dynamic_limit,
        "gram_condition": condition,
        "gram_inf_norm": gram_norm,
        "mapping_inf_norm": float(np.linalg.norm(mapping, np.inf)),
        "canonical_negative_overlap_inf_norm": float(np.linalg.norm(canonical, np.inf)),
        "backward_error_eta": eta,
        "backward_error_denominator": eta_denominator,
        "column_metrics": column_metrics,
        "column_absolute_errors": [item["absolute"] for item in column_metrics],
        "column_relative_errors": [item["relative"] for item in column_metrics],
        "worst_column": worst["index"],
        "worst_column_key": worst["key"],
        "worst_column_relative_error": worst["relative"],
        "worst_column_group": next(
            (
                group
                for group in payload.get("degenerate_groups", [])
                if isinstance(group, Mapping)
                and (
                    worst["index"] in group.get("indices", [])
                    or worst["key"] in group.get("keys", [])
                )
            ),
            "not_available",
        ),
        "repeat_backward_error_eta": repeat_eta,
        "repeat_backward_error_denominator": repeat_eta_denominator,
        "repeat_matrix_differences": repeat_differences,
        "raw_forward_error": raw_forward_recomputed,
        "raw_forward_error_reported": reported_raw_forward_error,
        "raw_forward_denominator": raw_forward_denominator,
        "representation_error": representation_recomputed,
        "representation_error_reported": reported_representation_error,
        "representation_denominator": representation_denominator,
        "repeat_raw_forward_error": repeat_raw_forward,
        "repeat_raw_forward_denominator": repeat_raw_forward_denominator,
        "repeat_representation_error": repeat_representation,
        "repeat_representation_denominator": repeat_representation_denominator,
        "representation_epsilon": float(np.finfo(np.float64).eps),
        "historical": historical_entries,
        "gates": gates,
    }


__all__ = [
    "TASK039_GRID_TARGETS",
    "TASK039_M480_PROGRESS_ROWS",
    "audit_m960_trace",
    "check_m480_hybrid_iterative",
    "compare_full3d_grid_views",
    "diagnose_h_paths",
    "load_full3d_grid_view",
    "mesh_resource_preflight",
]
