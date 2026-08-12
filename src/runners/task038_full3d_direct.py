"""Task38 Full3D direct adapter for the existing ordinary stage entrypoints."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import simulation_config_3d_from_normalized


def _run_solver(
    cfg: Any,
    numerical_output: Path,
    *,
    canonical_vector_export: bool,
) -> dict[str, Any]:
    if cfg.stage_case == "stage1_airbox":
        from src.solvers.solve_maxwell_3d_stage_1_airbox import (
            run_stage1_airbox_3d_case,
        )

        return run_stage1_airbox_3d_case(cfg, numerical_output)
    if cfg.stage_case == "floquet_airbox":
        from src.solvers.solve_maxwell_3d_stage_2a_floquet_airbox import (
            run_stage2a_floquet_airbox_3d_case,
        )

        return run_stage2a_floquet_airbox_3d_case(cfg, numerical_output)
    if cfg.stage_case == "pml_airbox":
        from src.solvers.solve_maxwell_3d_stage_2b_pml_airbox import (
            run_stage2b_pml_airbox_3d_case,
        )

        return run_stage2b_pml_airbox_3d_case(cfg, numerical_output)
    if cfg.stage_case == "fresnel_interface":
        from src.solvers.solve_maxwell_3d_stage_2c_fresnel_interface import (
            run_stage2c_fresnel_interface_3d_case,
        )

        return run_stage2c_fresnel_interface_3d_case(cfg, numerical_output)
    if cfg.stage_case == "stage4_flat_layer_sanity":
        from src.solvers.solve_maxwell_3d_stage_4a_flat_layer_sanity import (
            run_stage4a_flat_layer_sanity_3d_case,
        )

        return run_stage4a_flat_layer_sanity_3d_case(cfg, numerical_output)
    if cfg.stage_case == "stage4_block_grating":
        from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
            run_stage4b_block_grating_3d_case,
        )

        return run_stage4b_block_grating_3d_case(
            cfg,
            numerical_output,
            canonical_vector_export=canonical_vector_export,
        )
    raise ValueError(f"unsupported Full3D direct stage {cfg.stage_case!r}")


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _generic_authority_errors(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("case_status") != "completed":
        errors.append("numerical summary case_status is not completed")
    if summary.get("official_result") is not True:
        errors.append("numerical summary official_result is not true")
    residual = summary.get("linear_system_relative_residual")
    if (
        not _finite_number(residual)
        or float(residual) < 0.0
        or float(residual) > 1.0e-9
    ):
        errors.append("linear-system residual is outside the Full3D authority limit")
    return errors


def _stage4_authority_errors(summary: Mapping[str, Any]) -> list[str]:
    errors = _generic_authority_errors(summary)
    for key in ("R_total", "T_total", "A_volume_total"):
        if not _finite_number(summary.get(key)):
            errors.append(f"numerical summary lacks finite {key}")
    return errors


def run_full3d_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    solver_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one connected Full3D direct stage and inspect its returned summary."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("full3d_direct requires dimension=3")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_direct":
        raise ValueError("full3d_direct requires method.kind=full3d_direct")
    solver = resolved_payload.get("solver")
    if not isinstance(solver, Mapping) or solver.get("linear_solver") != "direct":
        raise ValueError("full3d_direct requires solver.linear_solver=direct")
    geometry = resolved_payload.get("geometry")
    allowed_geometry = {
        "airbox",
        "fresnel_interface",
        "flat_layer",
        "rectangular_block_grating",
    }
    if (
        not isinstance(geometry, Mapping)
        or geometry.get("geometry_kind") not in allowed_geometry
    ):
        raise ValueError("full3d_direct requires a supported 3D geometry")

    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case not in {
        "stage1_airbox",
        "floquet_airbox",
        "pml_airbox",
        "fresnel_interface",
        "stage4_flat_layer_sanity",
        "stage4_block_grating",
    }:
        raise ValueError(f"full3d_direct has no adapter for stage {cfg.stage_case!r}")
    if (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError("Full3D direct adapter requires a complete solve")

    output = resolved_payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("resolved output payload is missing")
    canonical_vector_export = bool(output.get("export_canonical_vectors", False))
    if canonical_vector_export and cfg.stage_case != "stage4_block_grating":
        raise ValueError(
            "canonical vectors are only connected for Stage4 block grating"
        )

    numerical_output = Path(run_directory).resolve() / "numerical_output"
    runner = solver_runner or _run_solver
    summary = runner(
        cfg,
        numerical_output,
        canonical_vector_export=canonical_vector_export,
    )
    if not isinstance(summary, Mapping):
        return {
            "passed": False,
            "errors": ["Full3D solver did not return a summary object"],
            "summary": None,
            "numerical_output_directory": str(numerical_output),
        }
    errors = (
        _stage4_authority_errors(summary)
        if cfg.stage_case in {"stage4_flat_layer_sanity", "stage4_block_grating"}
        else _generic_authority_errors(summary)
    )
    return {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["run_full3d_direct"]
