"""Task38 Full3D direct adapter for one resolved Stage4 input."""

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
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    return run_stage4b_block_grating_3d_case(
        cfg,
        numerical_output,
        canonical_vector_export=canonical_vector_export,
    )


def _authority_errors(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("case_status") != "completed":
        errors.append("numerical summary case_status is not completed")
    if summary.get("official_result") is not True:
        errors.append("numerical summary official_result is not true")
    residual = summary.get("linear_system_relative_residual")
    if not isinstance(residual, (int, float)) or isinstance(residual, bool):
        errors.append("numerical summary lacks a finite linear-system residual")
    elif not math.isfinite(float(residual)) or float(residual) > 1.0e-9:
        errors.append("linear-system residual exceeds the Full3D authority limit")
    for key in ("R_total", "T_total", "A_volume_total"):
        value = summary.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"numerical summary lacks finite {key}")
        elif not math.isfinite(float(value)):
            errors.append(f"numerical summary {key} is not finite")
    return errors


def run_full3d_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    solver_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the connected full3d_direct adapter and inspect solver authority."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("full3d_direct requires dimension=3")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_direct":
        raise ValueError("full3d_direct requires method.kind=full3d_direct")
    solver = resolved_payload.get("solver")
    if not isinstance(solver, Mapping) or solver.get("linear_solver") != "direct":
        raise ValueError("full3d_direct requires solver.linear_solver=direct")
    geometry = resolved_payload.get("geometry")
    if (
        not isinstance(geometry, Mapping)
        or geometry.get("geometry_kind") != "rectangular_block_grating"
    ):
        raise ValueError("full3d_direct requires a rectangular block grating")

    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case != "stage4_block_grating":
        raise ValueError("full3d_direct requires the Stage4 block-grating stage")
    if (
        cfg.matrix_diagnostics_assemble_only
        or cfg.matrix_diagnostics_factorization_only
    ):
        raise ValueError("Full3D direct adapter requires a complete solve")

    output = resolved_payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("resolved output payload is missing")
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    runner = solver_runner or _run_solver
    summary = runner(
        cfg,
        numerical_output,
        canonical_vector_export=bool(output.get("export_canonical_vectors", False)),
    )
    if not isinstance(summary, Mapping):
        return {
            "passed": False,
            "errors": ["Full3D solver did not return a summary object"],
            "summary": None,
            "numerical_output_directory": str(numerical_output),
        }
    errors = _authority_errors(summary)
    return {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["run_full3d_direct"]
