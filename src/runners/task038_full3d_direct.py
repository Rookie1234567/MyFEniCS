"""Task38 Full3D direct adapter for the existing ordinary stage entrypoints."""

from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from src.io.input_validation import simulation_config_3d_from_normalized


def _run_solver(
    cfg: Any,
    numerical_output: Path,
    *,
    canonical_vector_export: bool,
    solution_observer=None,
    pre_recovery_packet_directory: Path | None = None,
    pre_recovery_packet_identity: Mapping[str, Any] | None = None,
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
            solution_observer=solution_observer,
            canonical_vector_export=canonical_vector_export,
            pre_recovery_packet_directory=pre_recovery_packet_directory,
            pre_recovery_packet_identity=pre_recovery_packet_identity,
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


def _canonical_solution_observer(run_directory: Path):
    """Reuse the reviewed writer and expose a generic Full3D summary key."""

    from benchmarks.run_task033_full3d_watchdog import (
        task037_m3a_solution_observer,
    )

    reviewed_observer = task037_m3a_solution_observer(run_directory)

    def observe(**kwargs: Any) -> None:
        reviewed_observer(**kwargs)
        summary = kwargs["summary"]
        export = summary.pop("task037_m3a_canonical_export", None)
        if not isinstance(export, Mapping):
            raise ValueError("Full3D canonical observer did not produce an export")
        summary["full3d_direct_canonical_export"] = dict(export)

    return observe


def _pre_recovery_packet_identity(
    payload: Mapping[str, Any],
    *,
    source_sha: str | None,
    resolved_config_sha256: str | None,
) -> dict[str, Any]:
    """Build the small identity consumed by the pre-recovery packet writer."""

    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("pre-recovery lifecycle requires the complete source SHA")
    if not isinstance(resolved_config_sha256, str) or len(resolved_config_sha256) != 64:
        raise ValueError("pre-recovery lifecycle requires the resolved-config SHA")
    provenance = payload.get("provenance")
    derived = payload.get("derived")
    inventory = (
        derived.get("external_mode_inventory") if isinstance(derived, Mapping) else None
    )
    keys = inventory.get("keys") if isinstance(inventory, Mapping) else None
    if not isinstance(keys, list) or not isinstance(inventory.get("count"), int):
        raise ValueError(
            "pre-recovery lifecycle requires the resolved external inventory"
        )
    normalized_keys = [dict(key) for key in keys]
    encoded_keys = [
        json.dumps(key, sort_keys=True, separators=(",", ":"))
        for key in normalized_keys
    ]
    if inventory["count"] != len(normalized_keys) or len(set(encoded_keys)) != len(
        normalized_keys
    ):
        raise ValueError("resolved external inventory must be exact and unique")
    if not isinstance(provenance, Mapping):
        raise ValueError("pre-recovery lifecycle requires resolved provenance")
    execution = payload["execution"]
    incidence = payload["incidence"]
    discretization = payload["discretization"]
    return {
        "schema": "task039.v4.pre_recovery.identity.v1",
        "source_sha": source_sha,
        "input_sha256": provenance["input_sha256"],
        "physical_model_sha256": provenance["physical_model_sha256"],
        "resolved_config_sha256": resolved_config_sha256,
        "model_id": payload["model_id"],
        "run_id": payload["run_id"],
        "dimension": payload["dimension"],
        "method": payload["method"]["kind"],
        "mpi_size": execution["mpi_size"],
        "wavelength_nm": incidence["wavelength_nm"],
        "grazing_angle_deg": incidence.get("grazing_angle_deg"),
        "azimuth_deg": incidence.get("azimuth_deg"),
        "polarization": incidence["polarization"],
        "nedelec_degree": discretization["nedelec_degree"],
        "mesh_target_nm": discretization["mesh_target_nm"],
        "external_mode_inventory": {
            "count": len(normalized_keys),
            "keys": normalized_keys,
        },
    }


def _canonical_authority_errors(summary: Mapping[str, Any]) -> list[str]:
    from benchmarks.canonical_vector_artifacts import MANIFEST_SCHEMA

    export = summary.get("full3d_direct_canonical_export")
    if not isinstance(export, Mapping):
        return ["Full3D canonical export summary is missing"]
    roles = export.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != {"active_trace", "full_fe"}:
        return ["Full3D canonical export roles must be active_trace and full_fe"]
    errors: list[str] = []
    for role_name in ("active_trace", "full_fe"):
        role = roles.get(role_name)
        if not isinstance(role, Mapping):
            errors.append(f"canonical role {role_name} is missing")
            continue
        manifest = role.get("manifest")
        manifest_path = Path(manifest) if isinstance(manifest, str) else None
        if manifest_path is not None and not manifest_path.is_absolute():
            manifest_path = Path(__file__).resolve().parents[2] / manifest_path
        digest = role.get("manifest_sha256")
        packet_count = role.get("global_summed_packet_count")
        if (
            manifest_path is None
            or not manifest_path.is_file()
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != digest
        ):
            errors.append(f"canonical role {role_name} manifest/hash is invalid")
        if (
            not isinstance(packet_count, int)
            or isinstance(packet_count, bool)
            or packet_count <= 0
        ):
            errors.append(f"canonical role {role_name} packet count is invalid")
        if role.get("schema_version") != MANIFEST_SCHEMA:
            errors.append(f"canonical role {role_name} schema is invalid")
    return errors


def run_full3d_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    solver_runner: Callable[..., dict[str, Any]] | None = None,
    source_sha: str | None = None,
    resolved_config_sha256: str | None = None,
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
    lifecycle = resolved_payload.get("solver", {}).get(
        "direct_factor_lifecycle", "retain_until_postprocess"
    )
    packet_directory = None
    packet_identity = None
    if lifecycle == "release_before_recovery":
        if not (
            resolved_payload.get("model_id") == "task039_5nm_v4_1deg_s5_full3d"
            and cfg.stage_case == "stage4_block_grating"
            and cfg.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
        ):
            raise ValueError(
                "release_before_recovery is limited to the Task39 V4 Stage4 profile"
            )
        packet_directory = (
            Path(run_directory).resolve() / "numerical_output" / "pre_recovery_packet"
        )
        packet_identity = _pre_recovery_packet_identity(
            resolved_payload,
            source_sha=source_sha,
            resolved_config_sha256=resolved_config_sha256,
        )
    elif lifecycle != "retain_until_postprocess":
        raise ValueError(f"unsupported direct_factor_lifecycle={lifecycle!r}")
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
    solution_observer = (
        _canonical_solution_observer(numerical_output)
        if canonical_vector_export
        else None
    )
    runner_kwargs: dict[str, Any] = {
        "canonical_vector_export": canonical_vector_export,
    }
    if canonical_vector_export:
        runner_kwargs["solution_observer"] = solution_observer
    if packet_directory is not None:
        runner_kwargs.update(
            {
                "pre_recovery_packet_directory": packet_directory,
                "pre_recovery_packet_identity": packet_identity,
            }
        )
    summary = runner(
        cfg,
        numerical_output,
        **runner_kwargs,
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
    if canonical_vector_export:
        errors.extend(_canonical_authority_errors(summary))
    return {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "numerical_output_directory": str(numerical_output),
    }


__all__ = ["run_full3d_direct"]
