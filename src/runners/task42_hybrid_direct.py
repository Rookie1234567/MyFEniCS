"""Task42 A2 Hybrid-direct adapter over the shared Task32 condensed kernel."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from src.io.input_validation import (
    TASK42_13P5_HYBRID_MODEL_ID,
    simulation_config_3d_from_normalized,
    task42_hybrid_direct_profile_errors,
)
from src.runners.task038_hybrid_direct import (
    _append_source_attestation,
    _argv_for_payload,
)

Task42HybridRunner = Callable[..., Mapping[str, Any]]


def _default_runner(argv: list[str], cfg: Any, **kwargs: Any) -> Mapping[str, Any]:
    from benchmarks.run_task032_phase6_augmented import main

    return main(argv, config_override=cfg, use_case080_reference=False, **kwargs)


def run_task42_hybrid_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
    resolved_config_sha256: str,
    task42_phase_gate: Callable[..., Mapping[str, Any]],
    runner: Task42HybridRunner | None = None,
) -> dict[str, Any]:
    """Run the separately identified p6/h10/M120 Task42 A2 direct profile."""

    if resolved_payload.get("model_id") != TASK42_13P5_HYBRID_MODEL_ID:
        raise ValueError("Task42 Hybrid adapter received another model identity")
    errors = task42_hybrid_direct_profile_errors(resolved_payload)
    if errors:
        raise ValueError(f"Task42 Hybrid profile is invalid: {errors[0]}")
    if not callable(task42_phase_gate):
        raise TypeError("Task42 Hybrid adapter requires the phase-gate callback")
    method = resolved_payload.get("method")
    derived = resolved_payload.get("derived")
    provenance = resolved_payload.get("provenance")
    if not all(isinstance(value, Mapping) for value in (method, derived, provenance)):
        raise ValueError("Task42 Hybrid resolved identity is incomplete")
    inventory = derived.get("external_mode_inventory")
    material = derived.get("material_provenance")
    if not isinstance(inventory, Mapping) or not isinstance(material, Mapping):
        raise TypeError("Task42 Hybrid external keys or material identity are missing")
    if not isinstance(inventory.get("keys"), list) or not inventory["keys"]:
        raise ValueError("Task42 Hybrid full external mode inventory is empty")
    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.case_name != TASK42_13P5_HYBRID_MODEL_ID:
        raise ValueError("Task42 Hybrid numerical config identity differs from payload")
    run_root = Path(run_directory).resolve()
    numerical_output = run_root / "numerical_output"
    output_record = numerical_output / "run_summary.json"
    argv = _append_source_attestation(
        _argv_for_payload(resolved_payload, output_record), source_sha
    )
    output_identity = {
        "model_id": str(resolved_payload["model_id"]),
        "run_id": str(resolved_payload["run_id"]),
        "comparison_group": str(resolved_payload["comparison_group"]),
        "input_sha256": str(provenance["input_sha256"]),
        "physical_model_sha256": str(provenance["physical_model_sha256"]),
        "resolved_config_sha256": str(resolved_config_sha256),
        "source_sha": str(source_sha),
        "wavelength_nm": float(resolved_payload["incidence"]["wavelength_nm"]),
        "requested_modes_per_direction": int(
            method["requested_modes_per_direction"]
        ),
        "material_identity_sha256": str(material["material_identity_sha256"]),
        "material_record_sha256": str(material["material_record_sha256"]),
        "canonical_export_prefix": "task42_hybrid_direct",
        "sample_coordinates_source": "actual_main_selected_sample_x_y_z",
        "external_mode_inventory_identity": inventory.get("identity"),
    }
    run = runner or _default_runner
    record = run(
        argv,
        cfg,
        canonical_export_prefix="task42_hybrid_direct",
        external_mode_inventory=inventory,
        exact_one_cell_work_dir=numerical_output / "task42_exact_one_cell_traction",
        task42_hybrid_profile=True,
        task42_phase_gate=task42_phase_gate,
        task42_output_identity=output_identity,
    )
    if not isinstance(record, Mapping):
        return {
            "passed": False,
            "errors": ["shared Task32 runner returned no record"],
            "record": None,
            "argv": argv,
            "numerical_output_directory": str(numerical_output),
        }
    qualification = record.get("qualification")
    passed = (
        isinstance(qualification, Mapping)
        and qualification.get("integration_pass") is True
    )
    return {
        "passed": bool(passed),
        "errors": [] if passed else ["Task42 Hybrid numerical/physical gates did not pass"],
        "record": record,
        "argv": argv,
        "numerical_output_directory": str(numerical_output),
        "output_identity": output_identity,
    }


__all__ = ["run_task42_hybrid_direct"]
