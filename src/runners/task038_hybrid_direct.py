"""Task38 legacy augmented Hybrid direct adapter for the supported model pair."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Mapping

from src.common.config_3d import STANDARD_FULL_ASSEMBLY_BACKEND
from src.io.input_validation import simulation_config_3d_from_normalized


LegacyRunner = Callable[..., Mapping[str, Any]]


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _supported_output_errors(
    output: Mapping[str, Any], bottom_interface_nm: float, top_interface_nm: float
) -> list[str]:
    errors: list[str] = []
    for key in (
        "export_fields",
        "export_diffraction_orders",
        "export_modal_amplitudes",
        "export_reference_planes",
    ):
        if output.get(key) is not True:
            errors.append(
                f"output.{key}=true is required by the legacy augmented adapter"
            )
    if output.get("export_canonical_vectors") is not False:
        errors.append(
            "output.export_canonical_vectors=true is unsupported by the legacy runner"
        )
    if output.get("unique_output") is not True:
        errors.append(
            "output.unique_output=true is required by the legacy augmented adapter"
        )
    if (
        output.get("diffraction_order_max_m") != 2
        or output.get("diffraction_order_max_n") != 2
    ):
        errors.append("diffraction order reporting bounds must be 2 x 2")
    reference_planes = output.get("reference_plane_z_nm") or ()
    if not all(
        bottom_interface_nm <= float(value) <= top_interface_nm
        for value in reference_planes
    ):
        errors.append("reference planes must lie between the Hybrid interfaces")
    return errors


def _authority_errors(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    qualification = record.get("qualification")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("integration_pass") is not True
    ):
        errors.append("Hybrid direct record integration_pass is not true")

    solve = record.get("solve")
    residual = (
        solve.get("true_relative_residual") if isinstance(solve, Mapping) else None
    )
    if not _finite(residual) or float(residual) > 1.0e-9:
        errors.append("Hybrid direct true residual exceeds 1e-9")

    validation = record.get("validation")
    port_power = (
        validation.get("port_power") if isinstance(validation, Mapping) else None
    )
    field = record.get("physical_field_reconstruction")
    volume = field.get("volume_absorption") if isinstance(field, Mapping) else None
    if not isinstance(port_power, Mapping) or not isinstance(volume, Mapping):
        errors.append("Hybrid direct record lacks port-power or volume authority")
    else:
        for key in ("R_total", "T_total"):
            if not _finite(port_power.get(key)):
                errors.append(f"Hybrid direct record lacks finite {key}")
        if not _finite(volume.get("A_volume_total")):
            errors.append("Hybrid direct record lacks finite A_volume_total")
        if (
            not _finite(volume.get("energy_closure_error"))
            or abs(float(volume["energy_closure_error"])) > 1.0e-5
        ):
            errors.append("Hybrid direct energy closure exceeds 1e-5")

    orders = (
        validation.get("external_diffraction_orders")
        if isinstance(validation, Mapping)
        else None
    )
    if (
        not isinstance(orders, list)
        or not orders
        or not all(
            isinstance(item, Mapping)
            and "m" in item
            and "n" in item
            and _finite(item.get("power_ratio"))
            for item in orders
        )
    ):
        errors.append("Hybrid direct diffraction-order inventory is incomplete")
    return errors


def _argv_for_payload(payload: Mapping[str, Any], output_record: Path) -> list[str]:
    incidence = payload["incidence"]
    discretization = payload["discretization"]
    method = payload["method"]
    return [
        "--output",
        str(output_record),
        "--h-nm",
        str(discretization["mesh_target_nm"]),
        "--degree",
        str(discretization["nedelec_degree"]),
        "--modal-h-nm",
        str(discretization["mesh_target_nm"]),
        "--modal-degree",
        str(discretization["nedelec_degree"]),
        "--bottom-interface-nm",
        str(method["bottom_interface_nm"]),
        "--top-interface-nm",
        str(method["top_interface_nm"]),
        "--incident-grazing-deg",
        str(incidence["grazing_angle_deg"]),
        "--polarization-kind",
        str(incidence["polarization"]),
        "--requested-modes",
        str(method["requested_modes_per_direction"]),
        "--candidate-modes",
        str(2 * int(method["requested_modes_per_direction"])),
        "--internal-propagation-model",
        str(method["propagation_model"]),
        "--internal-traction-model",
        str(method["traction_model"]),
        "--stage4-full3d-assembly-backend",
        str(discretization["assembly_backend"]),
        "--solver-path",
        "augmented",
    ]


def _append_source_attestation(argv: list[str], source_sha: str | None) -> list[str]:
    if source_sha is None:
        return argv
    return [*argv, "--verified-clean-sha", source_sha]


def _default_legacy_runner(argv: list[str], cfg: Any) -> Mapping[str, Any]:
    from benchmarks.run_task032_phase6_augmented import main

    return main(
        argv,
        config_override=cfg,
        use_case080_reference=False,
    )


def run_hybrid_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    runner: LegacyRunner | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    """Run the legacy augmented Hybrid direct supported continuous model pair."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("hybrid_direct requires dimension=3")
    method = resolved_payload.get("method")
    solver = resolved_payload.get("solver")
    geometry = resolved_payload.get("geometry")
    boundary = resolved_payload.get("boundary")
    discretization = resolved_payload.get("discretization")
    if not isinstance(method, Mapping) or method.get("kind") != "hybrid_direct":
        raise ValueError("hybrid_direct requires method.kind=hybrid_direct")
    if not isinstance(solver, Mapping) or solver.get("linear_solver") != "direct":
        raise ValueError("hybrid_direct requires solver.linear_solver=direct")
    if solver.get("direct_solver_profile") != "default":
        raise ValueError("hybrid_direct only supports direct_solver_profile=default")
    if (
        method.get("propagation_model") != "continuous_beta"
        or method.get("traction_model") != "continuous_qep_beta"
    ):
        raise ValueError(
            "hybrid_direct supports only continuous_beta + continuous_qep_beta"
        )
    if (
        not isinstance(geometry, Mapping)
        or geometry.get("geometry_kind") != "rectangular_block_grating"
    ):
        raise ValueError("hybrid_direct requires a rectangular block grating")
    if (
        not isinstance(boundary, Mapping)
        or boundary.get("vertical_boundary") != "dtn_port"
    ):
        raise ValueError("hybrid_direct requires vertical_boundary=dtn_port")
    if (
        boundary.get("dtn_assembly") != "auxiliary"
        or boundary.get("use_pml") is not False
    ):
        raise ValueError("hybrid_direct requires auxiliary DtN without PML")
    if (
        not isinstance(discretization, Mapping)
        or discretization.get("assembly_backend") != STANDARD_FULL_ASSEMBLY_BACKEND
    ):
        raise ValueError("hybrid_direct requires assembly_backend=standard_full")

    output = resolved_payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("hybrid_direct output payload is missing")
    output_errors = _supported_output_errors(
        output,
        float(method["bottom_interface_nm"]),
        float(method["top_interface_nm"]),
    )
    if output_errors:
        raise ValueError("; ".join(output_errors))

    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case != "stage4_block_grating" or not cfg.use_floquet_xy:
        raise ValueError("hybrid_direct requires the Stage4 dual-Floquet config")
    if cfg.nedelec_degree not in {1, 2, 3, 4}:
        raise ValueError("hybrid_direct supports degrees 1 through 4")
    if int(method["requested_modes_per_direction"]) < 2:
        raise ValueError("hybrid_direct requires at least two modes per direction")
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    output_record = numerical_output / "run_summary.json"
    argv = _append_source_attestation(
        _argv_for_payload(resolved_payload, output_record), source_sha
    )
    record = (runner or _default_legacy_runner)(argv, cfg)
    if not isinstance(record, Mapping):
        return {
            "passed": False,
            "errors": ["legacy Hybrid runner did not return a record"],
            "record": None,
            "numerical_output_directory": str(numerical_output),
            "argv": argv,
        }
    errors = _authority_errors(record)
    return {
        "passed": not errors,
        "errors": errors,
        "record": record,
        "numerical_output_directory": str(numerical_output),
        "argv": argv,
    }


__all__ = ["run_hybrid_direct"]
