"""Finite Task39 Hybrid-direct adapter over the existing augmented runner."""

from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import (
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
    task039_model_id_matches,
    task039_profile_errors,
)
from src.runners.task038_hybrid_direct import (
    _append_source_attestation,
    _argv_for_payload,
)


Task039Runner = Callable[[list[str], Any, str, Mapping[str, Any]], Mapping[str, Any]]
TASK039_HYBRID_MODE_CANDIDATES = (120, 240, 480, 960)


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


def _authority_errors(
    record: Mapping[str, Any],
    expected_inventory: Mapping[str, Any],
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
) -> Mapping[str, Any]:
    from benchmarks.run_task032_phase6_augmented import main

    return main(
        argv,
        config_override=cfg,
        use_case080_reference=False,
        canonical_export_prefix=canonical_export_prefix,
        external_mode_inventory=external_mode_inventory,
    )


def run_task039_hybrid_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    runner: Task039Runner | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Run one finite Task39 p6/h10 Hybrid-direct profile."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("Task39 Hybrid direct requires dimension=3")
    model_id = str(resolved_payload.get("model_id", ""))
    if not task039_model_id_matches("hybrid_direct", model_id):
        raise ValueError("Task39 Hybrid direct requires a task039_5nm model_id")
    if resolved_payload.get("method", {}).get("kind") != "hybrid_direct":
        raise ValueError("Task39 Hybrid direct requires method.kind=hybrid_direct")
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

    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case != "stage4_block_grating" or not cfg.use_floquet_xy:
        raise ValueError("Task39 Hybrid direct requires the Stage4 dual-Floquet config")
    inventory = task039_dynamic_external_mode_inventory(resolved_payload)
    expected_inventory = deepcopy(inventory)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    output_record = numerical_output / "run_summary.json"
    argv = _append_source_attestation(
        _argv_for_payload(resolved_payload, output_record), source_sha
    )
    invoke = runner or _default_runner
    record = invoke(argv, cfg, "task039_direct", inventory)
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
    errors = _authority_errors(record, expected_inventory)
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
