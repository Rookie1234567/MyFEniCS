"""Thin Task39 Full3D iterative adapter for the accepted M3a action core."""

from __future__ import annotations

import math
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import (
    simulation_config_3d_from_normalized,
    task039_dynamic_external_mode_inventory,
    task039_model_id_matches,
    task039_profile_errors,
)


TASK039_SCREEN_ITERATIONS = 4000
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")


def _task039_solver_profile(source_sha: str | None) -> dict[str, Any]:
    return {
        "screen_iterations": TASK039_SCREEN_ITERATIONS,
        "restart": 90,
        "relative_tolerance": 1.0e-6,
        "initial_guess": "zero",
        "preconditioner": "full3d_m3a_physical_slab_two_level",
        "canonical_vector_export": True,
        "source_sha": source_sha,
    }


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _authority_errors(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("case_status") != "completed":
        errors.append("Task39 Full3D iterative summary is not completed")
    if summary.get("official_result") is not True:
        errors.append("Task39 Full3D iterative summary is not official")
    residual_values = {
        "linear_system_relative_residual": summary.get(
            "linear_system_relative_residual"
        )
    }
    if summary.get("external_linear_solver_port") is not True:
        errors.append("external solver port was not used")
    if summary.get("ksp_converged") is not True:
        errors.append("external solver KSP did not converge")
    if summary.get("global_A_materialized") is not False:
        errors.append("global A materialization is not false")
    if summary.get("global_F_materialized") is not False:
        errors.append("global F materialization is not false")
    if summary.get("external_solver_profile") != (
        "never_materialized_owner_local_overlap0125_partition"
    ):
        errors.append(
            "summary external solver profile is not the accepted M3a action profile"
        )
    if summary.get("stage4_energy_balance_pass") is not True:
        errors.append("stage4 energy balance did not pass")
    closure = summary.get("energy_closure_error_port_volume")
    if not _finite_number(closure) or abs(float(closure)) > 1.0e-5:
        errors.append("stage4 energy closure exceeds 1e-5 or is missing")
    audit = summary.get("task039_m3a_core_audit")
    if not isinstance(audit, Mapping):
        errors.append("Task39 M3a core audit is missing")
    else:
        candidate = audit.get("candidate")
        if not isinstance(candidate, Mapping) or {
            key: candidate.get(key) for key in ("restart", "rtol", "max_it")
        } != {"restart": 90, "rtol": 1.0e-6, "max_it": TASK039_SCREEN_ITERATIONS}:
            errors.append("Task39 M3a candidate budget is not 4000/90/1e-6")
        if audit.get("solver_profile") != (
            "never_materialized_owner_local_overlap0125_partition"
        ):
            errors.append("Task39 M3a audit profile is missing")
        for name in (
            "reported_relative_residual",
            "condensed_true_residual",
            "full_augmented_true_residual",
        ):
            value = audit.get(f"external_{name}")
            if value is None:
                final = audit.get("final")
                value = final.get(name) if isinstance(final, Mapping) else None
            residual_values[f"external_{name}"] = value
        inventory = audit.get("no_global_factor_inventory")
        if (
            not isinstance(inventory, Mapping)
            or inventory.get("global_direct_factor_count") != 0
        ):
            errors.append("Task39 M3a no-factor audit is missing")
    for name, value in residual_values.items():
        if not _finite_number(value) or not 0.0 <= float(value) <= 1.0e-6:
            errors.append(f"{name} exceeds 1e-6 or is missing")
    canonical = summary.get("task037_m3a_canonical_export")
    roles = canonical.get("roles") if isinstance(canonical, Mapping) else None
    if not isinstance(roles, Mapping) or not {
        "active_trace",
        "full_fe",
    }.issubset(roles):
        errors.append("Task39 canonical active/full roles are missing")
    return errors


def _run_m3a_solver(
    cfg: Any,
    numerical_output: Path,
    *,
    screen_iterations: int,
    canonical_vector_export: bool,
    solution_observer: Callable[..., Any] | None = None,
    audit_observer: Callable[..., Any] | None = None,
) -> Mapping[str, Any]:
    """Reuse Stage4B and the src-level accepted action-only M3a port."""

    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )
    from src.solvers.static_condensed_iterative import (
        build_never_materialized_overlap0125_partition_port,
    )

    port = build_never_materialized_overlap0125_partition_port(
        screen_iterations=screen_iterations,
        audit_observer=audit_observer,
    )
    return run_stage4b_block_grating_3d_case(
        cfg,
        numerical_output,
        solution_observer=solution_observer,
        linear_solver_port=port,
        static_retain_local_schur_for_matrix_free=True,
        canonical_vector_export=canonical_vector_export,
    )


def run_full3d_iterative(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str | None = None,
    solution_observer_factory: Callable[[Path], Callable[..., Any]] | None = None,
    solver_runner: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the finite Task39 Full3D iterative profile and inspect its summary."""

    if resolved_payload.get("dimension") != 3:
        raise ValueError("full3d_iterative requires dimension=3")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_iterative":
        raise ValueError("full3d_iterative requires method.kind=full3d_iterative")
    if not task039_model_id_matches(
        "full3d_iterative", str(resolved_payload.get("model_id", ""))
    ):
        raise ValueError("full3d_iterative is connected only for Task39 profiles")
    if source_sha is None or not _SOURCE_SHA.fullmatch(source_sha):
        raise ValueError(
            "full3d_iterative requires a 40-character lowercase source SHA"
        )

    profile_errors = task039_profile_errors(resolved_payload)
    if profile_errors:
        raise ValueError(
            "Task39 Full3D iterative profile rejected: "
            + "; ".join(f"{path}: {message}" for path, message in profile_errors)
        )
    cfg = simulation_config_3d_from_normalized(resolved_payload)
    if cfg.stage_case != "stage4_block_grating":
        raise ValueError("Task39 Full3D iterative requires Stage4 block grating")

    output = resolved_payload.get("output")
    if (
        not isinstance(output, Mapping)
        or output.get("export_canonical_vectors") is not True
    ):
        raise ValueError("Task39 Full3D iterative requires canonical export")
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    inventory = task039_dynamic_external_mode_inventory(resolved_payload)
    if solution_observer_factory is None:
        from benchmarks.run_task033_full3d_watchdog import (
            task037_m3a_solution_observer,
        )

        solution_observer_factory = task037_m3a_solution_observer
    base_observer = solution_observer_factory(numerical_output)
    solver_profile = _task039_solver_profile(source_sha)

    def audit_observer(request: Any, snapshot: Any, audit: dict[str, Any]) -> None:
        comm = request.operator.getComm().tompi4py()
        if comm.rank == 0:
            audit = dict(audit)
            audit["external_reported_relative_residual"] = float(
                snapshot.reported_relative_residual
            )
            audit["external_condensed_true_residual"] = float(
                snapshot.condensed_true_residual
            )
            audit["external_full_augmented_true_residual"] = float(
                snapshot.full_augmented_true_residual
            )
            (numerical_output / "task039_m3a_core_audit.json").write_text(
                json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        comm.barrier()

    def solution_observer(**kwargs: Any) -> None:
        base_observer(**kwargs)
        summary = kwargs["summary"]
        audit_path = numerical_output / "task039_m3a_core_audit.json"
        if audit_path.is_file():
            summary["task039_m3a_core_audit"] = json.loads(
                audit_path.read_text(encoding="utf-8")
            )
        summary["external_mode_inventory"] = inventory
        summary["task039_solver_profile"] = solver_profile

    runner = solver_runner or _run_m3a_solver
    summary = runner(
        cfg,
        numerical_output,
        screen_iterations=TASK039_SCREEN_ITERATIONS,
        canonical_vector_export=True,
        solution_observer=solution_observer,
        audit_observer=audit_observer,
    )
    if not isinstance(summary, Mapping):
        return {
            "passed": False,
            "errors": ["Full3D iterative solver did not return a summary object"],
            "summary": None,
            "external_mode_inventory": inventory,
            "numerical_output_directory": str(numerical_output),
        }
    summary = dict(summary)
    summary["external_mode_inventory"] = inventory
    summary["task039_solver_profile"] = solver_profile
    errors = _authority_errors(summary)
    return {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "external_mode_inventory": inventory,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["TASK039_SCREEN_ITERATIONS", "run_full3d_iterative"]
