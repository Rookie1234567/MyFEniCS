"""Task38 ordinary 2D adapter for the existing TM/TE solver entrypoints."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import simulation_config_2d_from_normalized


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _authority_errors(
    summary: Mapping[str, Any], output: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    residual = summary.get("reduced_linear_residual")
    if not _finite(residual) or not 0.0 <= float(residual) <= 1.0e-9:
        errors.append("2D solver reduced residual exceeds 1e-9")
    if output.get("compute_power_metrics"):
        metrics = summary.get("power_metrics")
        if not isinstance(metrics, Mapping):
            errors.append("2D requested power metrics are missing")
        else:
            for key in ("R_total", "T_total", "R_plus_T"):
                if not _finite(metrics.get(key)):
                    errors.append(
                        f"2D requested power metric {key} is missing or non-finite"
                    )
    return errors


def _run_solver(
    cfg: Any, output_directory: Path, constraint_backend: str
) -> Mapping[str, Any]:
    from src.solvers.solve_port_maxwell import run_port_case
    from src.solvers.solve_te_maxwell import run_te_case, run_te_port_case
    from src.solvers.solve_vector_maxwell import run_case

    if cfg.calculation_method == "scattered":
        runner = run_te_case if cfg.polarization_type.upper() == "TE" else run_case
    elif cfg.polarization_type.upper() == "TE":
        runner = run_te_port_case
    else:
        runner = run_port_case
    return runner(cfg, output_directory, constraint_backend=constraint_backend)


def run_2d(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    solver_runner: Callable[[Any, Path, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one connected ordinary 2D method without a CLI round trip."""

    if resolved_payload.get("dimension") != 2:
        raise ValueError("2D adapter requires dimension=2")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") not in {
        "2d_scattered",
        "2d_port",
    }:
        raise ValueError("2D adapter requires method.kind=2d_scattered or 2d_port")
    solver = resolved_payload.get("solver")
    if not isinstance(solver, Mapping) or solver.get("linear_solver") != "direct":
        raise ValueError("2D adapter requires solver.linear_solver=direct")
    output = resolved_payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("resolved output payload is missing")
    cfg = simulation_config_2d_from_normalized(resolved_payload)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    runner = solver_runner or _run_solver
    summary = runner(cfg, numerical_output, str(method["constraint_backend"]))
    if not isinstance(summary, Mapping):
        return {
            "passed": False,
            "errors": ["2D solver did not return a summary object"],
            "summary": None,
            "numerical_output_directory": str(numerical_output),
        }
    errors = _authority_errors(summary, output)
    return {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["run_2d"]
