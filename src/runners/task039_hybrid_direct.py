"""Finite Task39 Hybrid-direct adapter over the existing augmented runner."""

from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from src.io.input_validation import (
    TASK039_E7_TRACE_FAMILY_SHA256,
    TASK039_M960_TRACE_GATE_POLICY,
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
    task039_model_id_matches,
    task039_profile_errors,
)
from src.runners.task038_hybrid_direct import (
    _append_source_attestation,
    _argv_for_payload,
)
from benchmarks.task039_memory_telemetry import (
    task039_v4_h4_hybrid_direct_formal_profile,
    task039_h5_hybrid_direct_formal_profile,
)


Task039Runner = Callable[[list[str], Any, str, Mapping[str, Any]], Mapping[str, Any]]
TASK039_HYBRID_MODE_CANDIDATES = (120, 240, 480, 960)
_TASK039_DIRECT_PAYLOAD_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "modal_amplitudes",
    "bottom_q",
    "top_q",
)


def select_task039_hybrid_mode(
    gates: Mapping[int, Mapping[str, bool]],
) -> dict[str, Any]:
    """Select the first finite M with its adjacent and Full3D gates."""

    if any(int(mode) not in TASK039_HYBRID_MODE_CANDIDATES for mode in gates):
        raise ValueError("Task39 Hybrid direct mode candidates stop at M=960")
    for mode, next_mode in ((120, 240), (240, 480), (480, 960)):
        current = gates.get(mode, {})
        if (
            current.get("own") is True
            and current.get("vs_next") is True
            and current.get("full3d") is True
        ):
            return {
                "status": "established",
                "selected_m": mode,
                "comparison_m": next_mode,
            }
    upper = gates.get(960, {})
    if upper.get("own") is True and upper.get("full3d") is True:
        return {"status": "upper_cap", "selected_m": 960}
    return {"status": "not_established", "selected_m": None}


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _finite_complex(value: Any) -> bool:
    return (
        isinstance(value, complex)
        and math.isfinite(value.real)
        and math.isfinite(value.imag)
    )


def _order_key(item: Mapping[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(item["side"]),
        int(item["m"]),
        int(item["n"]),
        str(item["polarization"]),
    )


def _inventory_keys(inventory: Mapping[str, Any]) -> tuple[tuple[Any, ...], ...]:
    keys = inventory.get("keys")
    if not isinstance(keys, list):
        return ()
    return tuple(
        (
            str(item["side"]),
            int(item["m"]),
            int(item["n"]),
            str(item["polarization"]),
        )
        for item in keys
        if isinstance(item, Mapping) and {"side", "m", "n", "polarization"} <= set(item)
    )


def _array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_errors(
    payload: Any,
    numerical_output: Path,
    record: Mapping[str, Any],
    expected_inventory: Mapping[str, Any],
) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["Task39 Hybrid direct comparison payload is missing"]
    errors: list[str] = []
    if payload.get("schema") != "task039.hybrid-direct-payload.v1":
        errors.append("Task39 Hybrid direct payload schema is invalid")
    if payload.get("keys") != list(_TASK039_DIRECT_PAYLOAD_KEYS):
        errors.append("Task39 Hybrid direct payload keys are invalid")
    path_value = payload.get("path")
    relative_path = Path(path_value) if isinstance(path_value, str) else None
    root = numerical_output.resolve()
    if (
        relative_path is None
        or relative_path.is_absolute()
        or ".." in relative_path.parts
        or len(relative_path.parts) != 1
    ):
        return errors + ["Task39 Hybrid direct payload path is not output-local"]
    payload_path = (root / relative_path).resolve()
    if payload_path.parent != root or not payload_path.is_file():
        return errors + [
            "Task39 Hybrid direct payload file is missing or escapes output"
        ]
    if payload.get("sha256") != _file_sha256(payload_path):
        errors.append("Task39 Hybrid direct payload file SHA256 mismatches")
    if payload.get("bytes") != payload_path.stat().st_size:
        errors.append("Task39 Hybrid direct payload byte count mismatches")

    counts = expected_inventory.get("counts", {})
    side_counts = counts.get("per_side", {}) if isinstance(counts, Mapping) else {}
    hybrid_system = record.get("hybrid_system")
    internal_unknown_count = (
        hybrid_system.get("internal_unknown_count")
        if isinstance(hybrid_system, Mapping)
        else None
    )
    expected_shapes = {
        "x_nm": (40,),
        "y_nm": (20,),
        "z_nm": (5,),
        "E_V_per_m": (5, 20, 40, 3),
        "H_A_per_m": (5, 20, 40, 3),
        "modal_amplitudes": (
            (int(internal_unknown_count),)
            if isinstance(internal_unknown_count, int)
            and not isinstance(internal_unknown_count, bool)
            else None
        ),
        "bottom_q": (
            (int(side_counts["bottom"]),)
            if isinstance(side_counts, Mapping) and "bottom" in side_counts
            else None
        ),
        "top_q": (
            (int(side_counts["top"]),)
            if isinstance(side_counts, Mapping) and "top" in side_counts
            else None
        ),
    }
    expected_dtypes = {
        key: ("float64" if key.endswith("_nm") else "complex128")
        for key in _TASK039_DIRECT_PAYLOAD_KEYS
    }
    metadata = payload.get("arrays")
    if not isinstance(metadata, Mapping) or set(metadata) != set(
        _TASK039_DIRECT_PAYLOAD_KEYS
    ):
        errors.append("Task39 Hybrid direct payload array metadata is incomplete")
        metadata = {}
    try:
        with np.load(payload_path, allow_pickle=False) as archive:
            if archive.files != list(_TASK039_DIRECT_PAYLOAD_KEYS):
                errors.append("Task39 Hybrid direct payload NPZ keys are invalid")
            for key in _TASK039_DIRECT_PAYLOAD_KEYS:
                if key not in archive:
                    continue
                array = np.asarray(archive[key])
                item = metadata.get(key)
                if not isinstance(item, Mapping):
                    errors.append(
                        f"Task39 Hybrid direct payload metadata missing {key}"
                    )
                    continue
                if expected_shapes[key] is None or array.shape != expected_shapes[key]:
                    errors.append(
                        f"Task39 Hybrid direct payload {key} shape is invalid"
                    )
                if str(array.dtype) != expected_dtypes[key]:
                    errors.append(
                        f"Task39 Hybrid direct payload {key} dtype is invalid"
                    )
                if not np.all(np.isfinite(array)):
                    errors.append(f"Task39 Hybrid direct payload {key} is not finite")
                if item.get("shape") != list(array.shape):
                    errors.append(
                        f"Task39 Hybrid direct payload {key} shape metadata mismatches"
                    )
                if item.get("dtype") != str(array.dtype):
                    errors.append(
                        f"Task39 Hybrid direct payload {key} dtype metadata mismatches"
                    )
                if item.get("bytes") != int(array.nbytes):
                    errors.append(
                        f"Task39 Hybrid direct payload {key} byte metadata mismatches"
                    )
                if item.get("sha256") != _array_sha256(array):
                    errors.append(
                        f"Task39 Hybrid direct payload {key} SHA256 mismatches"
                    )
                if item.get("finite") is not True:
                    errors.append(
                        f"Task39 Hybrid direct payload {key} finite flag is false"
                    )
            if "z_nm" in archive and not np.array_equal(
                np.asarray(archive["z_nm"]),
                np.asarray([10, 30, 60, 90, 110], dtype=np.float64),
            ):
                errors.append("Task39 Hybrid direct payload z planes are invalid")
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"Task39 Hybrid direct payload cannot be read: {exc}")
    return errors


def _authority_errors(
    record: Mapping[str, Any],
    expected_inventory: Mapping[str, Any],
    numerical_output: Path,
) -> list[str]:
    errors: list[str] = []
    qualification = record.get("qualification")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("integration_pass") is not True
    ):
        errors.append("Task39 Hybrid direct integration_pass is not true")

    solve = record.get("solve")
    residual = (
        solve.get("true_relative_residual") if isinstance(solve, Mapping) else None
    )
    if not _finite(residual) or float(residual) > 1.0e-9:
        errors.append("Task39 Hybrid direct true residual exceeds 1e-9")

    validation = record.get("validation")
    port_power = (
        validation.get("port_power") if isinstance(validation, Mapping) else None
    )
    physical = record.get("physical_field_reconstruction")
    volume = (
        physical.get("volume_absorption") if isinstance(physical, Mapping) else None
    )
    if not isinstance(port_power, Mapping) or not isinstance(volume, Mapping):
        errors.append("Task39 Hybrid direct record lacks R/T/A-volume authority")
    else:
        for key in ("R_total", "T_total", "A_balance"):
            if not _finite(port_power.get(key)):
                errors.append(f"Task39 Hybrid direct lacks finite {key}")
        if not _finite(volume.get("A_volume_total")):
            errors.append("Task39 Hybrid direct lacks finite A_volume_total")
        closure = volume.get("energy_closure_error")
        if not _finite(closure) or abs(float(closure)) > 1.0e-5:
            errors.append("Task39 Hybrid direct energy closure exceeds 1e-5")
        projection = validation.get("interface_e_projection")
        if (
            not isinstance(projection, Mapping)
            or not _finite(projection.get("combined_relative_residual"))
            or projection["combined_relative_residual"] > 1.0e-8
        ):
            errors.append("Task39 Hybrid direct interface projection exceeds 1e-8")
        traction = validation.get("fe_modal_traction_equilibrium")
        traction_pass = isinstance(traction, Mapping) and all(
            _finite(traction.get(f"{side}_relative_residual"))
            and traction[f"{side}_relative_residual"] <= 1.0e-8
            for side in ("bottom", "top")
        )
        if not traction_pass:
            errors.append("Task39 Hybrid direct exact traction exceeds 1e-8")
        gates = record.get("gates")
        for gate in (
            "interface_e_projection_relative_residual_le_1e-8",
            "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
            "assembled_interface_h_t_exact_dual_le_1e-8",
        ):
            if not isinstance(gates, Mapping) or gates.get(gate) is not True:
                errors.append(f"Task39 Hybrid direct gate {gate} is not true")

    canonical = record.get("canonical_exports")
    if not isinstance(canonical, Mapping) or set(canonical) != {"bottom", "top"}:
        errors.append("Task39 Hybrid direct canonical bottom/top exports are missing")
    else:
        for side in ("bottom", "top"):
            export = canonical.get(side)
            roles = export.get("roles") if isinstance(export, Mapping) else None
            if not isinstance(roles, Mapping) or set(roles) != {
                "active_trace",
                "full_fe",
            }:
                errors.append(
                    f"Task39 Hybrid direct canonical {side} roles are incomplete"
                )
            elif any(
                not isinstance(role, Mapping) or role.get("pass") is not True
                for role in roles.values()
            ):
                errors.append(f"Task39 Hybrid direct canonical {side} role failed")

    if record.get("external_mode_inventory") != dict(expected_inventory):
        errors.append("Task39 Hybrid direct external mode inventory is not exact")

    errors.extend(
        _payload_errors(
            physical.get("task039_direct_payload")
            if isinstance(physical, Mapping)
            else None,
            numerical_output,
            record,
            expected_inventory,
        )
    )

    orders = (
        validation.get("external_diffraction_orders")
        if isinstance(validation, Mapping)
        else None
    )
    expected_keys = _inventory_keys(expected_inventory)
    if not isinstance(orders, list):
        errors.append("Task39 Hybrid direct external diffraction orders are missing")
    else:
        observed_keys: list[tuple[str, int, int, str]] = []
        for item in orders:
            if not isinstance(item, Mapping) or not {
                "side",
                "m",
                "n",
                "polarization",
            } <= set(item):
                errors.append("Task39 Hybrid direct external order key is incomplete")
                continue
            try:
                observed_keys.append(_order_key(item))
            except (TypeError, ValueError):
                errors.append("Task39 Hybrid direct external order key is invalid")
                continue
            if not _finite(item.get("power_ratio")):
                errors.append("Task39 Hybrid direct external order power is not finite")
            for field in ("beta_per_nm", "total_projection", "outgoing_amplitude"):
                if not _finite_complex(item.get(field)):
                    errors.append(
                        f"Task39 Hybrid direct external order {field} is not finite complex"
                    )
        if len(observed_keys) != len(set(observed_keys)):
            errors.append("Task39 Hybrid direct external order keys are not unique")
        if tuple(sorted(observed_keys)) != tuple(sorted(expected_keys)):
            errors.append(
                "Task39 Hybrid direct external order keys do not match inventory"
            )
    return errors


def _default_runner(
    argv: list[str],
    cfg: Any,
    canonical_export_prefix: str,
    external_mode_inventory: Mapping[str, Any],
    exact_one_cell_work_dir: Path,
    trace_audit_capture_dir: str | Path | None = None,
    trace_audit_metadata: Mapping[str, Any] | None = None,
    canonical_trace_gate_policy: str | None = None,
    canonical_trace_family_sha256: str | None = None,
    task039_stage_marker_path: str | Path | None = None,
) -> Mapping[str, Any]:
    from benchmarks.run_task032_phase6_augmented import main

    kwargs: dict[str, Any] = {
        "config_override": cfg,
        "use_case080_reference": False,
        "canonical_export_prefix": canonical_export_prefix,
        "external_mode_inventory": external_mode_inventory,
        "exact_one_cell_work_dir": exact_one_cell_work_dir,
        "qep_solver_tolerance": 1.0e-12,
        "trace_audit_capture_dir": trace_audit_capture_dir,
        "trace_audit_metadata": trace_audit_metadata,
        "task039_stage_marker_path": task039_stage_marker_path,
    }
    if canonical_trace_gate_policy is not None:
        kwargs.update(
            {
                "canonical_trace_gate_policy": canonical_trace_gate_policy,
                "canonical_trace_family_sha256": canonical_trace_family_sha256,
            }
        )
    return main(
        argv,
        **kwargs,
    )


def run_task039_hybrid_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    runner: Task039Runner | None = None,
    source_sha: str | None = None,
    trace_audit_capture_dir: str | Path | None = None,
    trace_audit_metadata: Mapping[str, Any] | None = None,
    selected_mode_packet_consumer_manifest: str | Path | None = None,
    selected_mode_packet_consumer_identity_json: str | Path | None = None,
    selected_mode_packet_consumer_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run one finite Task39 Hybrid-direct profile."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("Task39 Hybrid direct requires dimension=3")
    model_id = str(resolved_payload.get("model_id", ""))
    if not task039_model_id_matches("hybrid_direct", model_id):
        raise ValueError("Task39 Hybrid direct requires a task039_5nm model_id")
    if resolved_payload.get("method", {}).get("kind") != "hybrid_direct":
        raise ValueError("Task39 Hybrid direct requires method.kind=hybrid_direct")
    method = resolved_payload["method"]
    canonical_trace_gate_policy = method.get("canonical_trace_gate_policy")
    canonical_trace_family_sha256 = method.get("canonical_trace_family_sha256")
    if (
        source_sha is None
        or len(source_sha) != 40
        or source_sha != source_sha.lower()
        or any(char not in "0123456789abcdef" for char in source_sha)
    ):
        raise ValueError(
            "Task39 Hybrid direct requires a 40-character lowercase source SHA"
        )
    profile_errors = task039_profile_errors(resolved_payload)
    if profile_errors:
        path, message = profile_errors[0]
        raise ValueError(f"{path}: {message}")
    if canonical_trace_gate_policy is not None and (
        canonical_trace_gate_policy != TASK039_M960_TRACE_GATE_POLICY
        or canonical_trace_family_sha256 != TASK039_E7_TRACE_FAMILY_SHA256
    ):
        raise ValueError("Task039 canonical trace Gate provenance is not approved.")
    packet_values = (
        selected_mode_packet_consumer_manifest,
        selected_mode_packet_consumer_identity_json,
        selected_mode_packet_consumer_manifest_sha256,
    )
    if any(value is not None for value in packet_values) and not all(
        value is not None for value in packet_values
    ):
        raise ValueError(
            "Task039 packet consumer requires manifest, identity JSON, and SHA256"
        )
    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case != "stage4_block_grating" or not cfg.use_floquet_xy:
        raise ValueError("Task39 Hybrid direct requires the Stage4 dual-Floquet config")
    inventory = task039_dynamic_external_mode_inventory(resolved_payload)
    expected_inventory = deepcopy(inventory)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    output_record = numerical_output / "run_summary.json"
    formal_stage_marker_path = None
    if trace_audit_capture_dir is None and (
        task039_h5_hybrid_direct_formal_profile(resolved_payload)
        or task039_v4_h4_hybrid_direct_formal_profile(resolved_payload)
    ):
        formal_stage_marker_path = numerical_output / "memory_stage_markers.raw.jsonl"
    argv = _append_source_attestation(
        _argv_for_payload(resolved_payload, output_record), source_sha
    )
    if trace_audit_capture_dir is not None:
        argv.extend(
            [
                "--memory-stages",
                str(numerical_output / "task039_trace_audit_stages.jsonl"),
            ]
        )
    if selected_mode_packet_consumer_manifest is not None:
        argv.extend(
            [
                "--selected-mode-packet-consumer-manifest",
                str(selected_mode_packet_consumer_manifest),
                "--selected-mode-packet-consumer-identity-json",
                str(selected_mode_packet_consumer_identity_json),
                "--selected-mode-packet-consumer-manifest-sha256",
                str(selected_mode_packet_consumer_manifest_sha256),
            ]
        )
    if runner is None:
        record = _default_runner(
            argv,
            cfg,
            "task039_direct",
            inventory,
            numerical_output / "exact_one_cell",
            trace_audit_capture_dir,
            {
                **dict(trace_audit_metadata or {}),
                "source_commit_sha": source_sha,
            },
            canonical_trace_gate_policy=canonical_trace_gate_policy,
            canonical_trace_family_sha256=canonical_trace_family_sha256,
            task039_stage_marker_path=formal_stage_marker_path,
        )
    else:
        if trace_audit_capture_dir is not None:
            raise ValueError("Trace audit capture requires the default Task039 runner.")
        record = runner(argv, cfg, "task039_direct", inventory)
    if not isinstance(record, Mapping):
        return {
            "passed": False,
            "errors": ["Task39 Hybrid direct runner did not return a record"],
            "record": None,
            "summary": None,
            "argv": argv,
            "external_mode_inventory": expected_inventory,
            "numerical_output_directory": str(numerical_output),
        }
    if canonical_trace_gate_policy is not None:
        record = dict(record)
        provenance = dict(record.get("provenance") or {})
        provenance.update(
            {
                "canonical_trace_gate_policy": canonical_trace_gate_policy,
                "canonical_trace_family_sha256": canonical_trace_family_sha256,
                "family_record_source": "tracked_compact_record",
            }
        )
        record["provenance"] = provenance
    if trace_audit_capture_dir is not None:
        if record.get("status") != "controlled_stop":
            return {
                "passed": False,
                "errors": ["Task039 trace capture did not controlled-stop"],
                "record": record,
                "summary": record,
                "argv": argv,
                "external_mode_inventory": expected_inventory,
                "numerical_output_directory": str(numerical_output),
                "result_classification": "task039_trace_capture_failed",
                "solver_qualified": False,
            }
        capture = record.get("trace_audit_capture", {})
        errors = []
        if capture.get("individual_capture_complete") is not True:
            errors.append("Task039 trace capture did not complete both endcaps")
        return {
            "passed": not errors,
            "errors": errors,
            "record": record,
            "summary": record,
            "argv": argv,
            "external_mode_inventory": expected_inventory,
            "numerical_output_directory": str(numerical_output),
            "result_classification": (
                "task039_trace_capture_complete"
                if not errors
                else "task039_trace_capture_failed"
            ),
            "solver_qualified": False,
        }
    errors = _authority_errors(record, expected_inventory, numerical_output)
    return {
        "passed": not errors,
        "errors": errors,
        "record": record,
        "summary": record,
        "argv": argv,
        "external_mode_inventory": expected_inventory,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = [
    "TASK039_HYBRID_MODE_CANDIDATES",
    "run_task039_hybrid_direct",
    "select_task039_hybrid_mode",
]
