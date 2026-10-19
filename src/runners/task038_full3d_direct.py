"""Task38 Full3D direct adapter for the existing ordinary stage entrypoints."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.io.input_validation import (
    TASK42_13P5_FULL3D_MODEL_ID,
    TASK42_DIRECT_FACTOR_LIFECYCLE,
    simulation_config_3d_from_normalized,
)
from src.io.resolved_config import canonical_json_bytes

TASK42_RECOVERY_ARCHIVE_SOURCE_SHA = "bafee20f02d2fdb04f34ad2c5f5ba33cb7215c3a"


def _run_solver(
    cfg: Any,
    numerical_output: Path,
    *,
    canonical_vector_export: bool,
    solution_observer=None,
    pre_recovery_packet_directory: Path | None = None,
    pre_recovery_packet_identity: Mapping[str, Any] | None = None,
    task42_stage_gate=None,
    task42_bridge_path: str | Path | None = None,
    task42_packet_recovery_manifest: Path | None = None,
    task42_packet_recovery_manifest_sha256: str | None = None,
    task42_packet_recovery_identity: Mapping[str, Any] | None = None,
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

        recovery_port = None
        if task42_packet_recovery_manifest is not None:
            from src.solvers.dtn_port_3d import task42_packet_recovery_port

            if (
                task42_packet_recovery_manifest_sha256 is None
                or task42_packet_recovery_identity is None
            ):
                raise ValueError("Task42 packet recovery bindings are incomplete")
            recovery_port = task42_packet_recovery_port(
                task42_packet_recovery_manifest,
                manifest_sha256=task42_packet_recovery_manifest_sha256,
                identity=task42_packet_recovery_identity,
            )

        return run_stage4b_block_grating_3d_case(
            cfg,
            numerical_output,
            solution_observer=solution_observer,
            canonical_vector_export=canonical_vector_export,
            pre_recovery_packet_directory=pre_recovery_packet_directory,
            pre_recovery_packet_identity=pre_recovery_packet_identity,
            task42_stage_gate=task42_stage_gate,
            task42_bridge_path=task42_bridge_path,
            task42_packet_recovery_manifest=task42_packet_recovery_manifest,
            task42_packet_recovery_manifest_sha256=(
                task42_packet_recovery_manifest_sha256
            ),
            task42_packet_recovery_identity=task42_packet_recovery_identity,
            linear_solver_port=recovery_port,
            matrix_free_dtn=recovery_port is not None,
        )
    raise ValueError(f"unsupported Full3D direct stage {cfg.stage_case!r}")


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _generic_authority_errors(
    summary: Mapping[str, Any], *, residual_limit: float = 1.0e-9
) -> list[str]:
    errors: list[str] = []
    if summary.get("case_status") != "completed":
        errors.append("numerical summary case_status is not completed")
    if summary.get("official_result") is not True:
        errors.append("numerical summary official_result is not true")
    residual = summary.get("linear_system_relative_residual")
    if (
        not _finite_number(residual)
        or float(residual) < 0.0
        or float(residual) > residual_limit
    ):
        errors.append(
            "linear-system residual is outside the Full3D authority limit "
            f"{residual_limit:.9g}"
        )
    return errors


def _stage4_authority_errors(
    summary: Mapping[str, Any], *, residual_limit: float = 1.0e-9
) -> list[str]:
    errors = _generic_authority_errors(summary, residual_limit=residual_limit)
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


def _task42_pre_recovery_packet_identity(
    payload: Mapping[str, Any],
    *,
    source_sha: str | None,
    resolved_config_sha256: str | None,
) -> dict[str, Any]:
    """Bind Task42's packet to its own model and resolved public input."""

    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("Task42 pre-recovery packet needs the complete source SHA")
    if not isinstance(resolved_config_sha256, str) or len(resolved_config_sha256) != 64:
        raise ValueError("Task42 pre-recovery packet needs the resolved-config SHA")
    if payload.get("model_id") != TASK42_13P5_FULL3D_MODEL_ID:
        raise ValueError("Task42 packet identity requires the registered model ID")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError(  # noqa: TRY004 - missing provenance is an invalid packet value
            "Task42 packet identity requires resolved provenance"
        )
    geometry = payload.get("geometry")
    materials = payload.get("materials")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    execution = payload.get("execution")
    method = payload.get("method")
    if not all(
        isinstance(value, Mapping)
        for value in (geometry, materials, incidence, discretization, execution, method)
    ):
        raise ValueError("Task42 packet identity is missing resolved physical fields")
    return {
        "schema": "task42.13p5.full3d.pre_recovery.identity.v1",
        "source_sha": source_sha,
        "input_sha256": provenance.get("input_sha256"),
        "physical_model_sha256": provenance.get("physical_model_sha256"),
        "resolved_config_sha256": resolved_config_sha256,
        "model_id": payload["model_id"],
        "run_id": payload.get("run_id"),
        "comparison_group": payload.get("comparison_group"),
        "dimension": payload.get("dimension"),
        "method": method.get("kind"),
        "mpi_size": execution.get("mpi_size"),
        "wavelength_nm": incidence.get("wavelength_nm"),
        "grazing_angle_deg": incidence.get("grazing_angle_deg"),
        "azimuth_deg": incidence.get("azimuth_deg"),
        "polarization": incidence.get("polarization"),
        "geometry": dict(geometry),
        "materials": dict(materials),
        "discretization": dict(discretization),
    }


def _task42_packet_recovery_expected_identity(
    payload: Mapping[str, Any],
    *,
    resolved_config_sha256: str,
    source_sha: str = TASK42_RECOVERY_ARCHIVE_SOURCE_SHA,
) -> dict[str, Any]:
    """Bind recovery to current physics/config and one qualified source identity."""

    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError(  # noqa: TRY004 - invalid resolved identity is an input-value refusal
            "Task42 packet recovery requires resolved provenance"
        )
    method = payload.get("method")
    geometry = payload.get("geometry")
    materials = payload.get("materials")
    incidence = payload.get("incidence")
    discretization = payload.get("discretization")
    execution = payload.get("execution")
    if not all(
        isinstance(value, Mapping)
        for value in (method, geometry, materials, incidence, discretization, execution)
    ):
        raise ValueError("Task42 packet recovery is missing resolved identity fields")
    return {
        "schema": "task42.13p5.full3d.pre_recovery.identity.v1",
        "source_sha": source_sha,
        "input_sha256": provenance.get("input_sha256"),
        "physical_model_sha256": provenance.get("physical_model_sha256"),
        "resolved_config_sha256": resolved_config_sha256,
        "model_id": payload.get("model_id"),
        "run_id": payload.get("run_id"),
        "comparison_group": payload.get("comparison_group"),
        "dimension": payload.get("dimension"),
        "method": method.get("kind"),
        "mpi_size": execution.get("mpi_size"),
        "wavelength_nm": incidence.get("wavelength_nm"),
        "grazing_angle_deg": incidence.get("grazing_angle_deg"),
        "azimuth_deg": incidence.get("azimuth_deg"),
        "polarization": incidence.get("polarization"),
        "geometry": dict(geometry),
        "materials": dict(materials),
        "discretization": dict(discretization),
    }


def _task42_output_only_delta_errors(
    archive_payload: Mapping[str, Any],
    effective_payload: Mapping[str, Any],
    *,
    allow_probe_override: bool,
) -> list[str]:
    """Allow only the two registered exterior diffraction-probe changes."""

    errors: list[str] = []
    archive_keys = set(archive_payload)
    effective_keys = set(effective_payload)
    if archive_keys != effective_keys:
        errors.append("resolved top-level fields changed")
    for key in archive_keys & effective_keys:
        if key == "output":
            continue
        if archive_payload[key] != effective_payload[key]:
            errors.append(f"resolved field {key!r} changed outside output probes")
    archive_output = archive_payload.get("output")
    effective_output = effective_payload.get("output")
    if not isinstance(archive_output, Mapping) or not isinstance(
        effective_output, Mapping
    ):
        errors.append("archive/effective output sections are not mappings")
    elif set(archive_output) != set(effective_output):
        errors.append("output fields changed beyond the registered probe values")
    else:
        allowed_output_fields = (
            {"top_probe_z_nm", "bottom_probe_z_nm"}
            if allow_probe_override
            else set()
        )
        if any(
            archive_output[key] != effective_output[key]
            for key in set(archive_output) - allowed_output_fields
        ):
            errors.append("an output field other than the two probes changed")
    return errors


def _task42_write_output_probe_receipts(
    *,
    comm: Any,
    numerical_output: Path,
    effective_output_bytes: bytes,
    identity_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Write Task42 output-only receipts on rank 0 and share the result."""

    effective_path = numerical_output / "effective_output_config.json"
    identity_path = numerical_output / "output_sampling_identity.json"
    identity_bytes = b""
    try:
        if not isinstance(effective_output_bytes, bytes):
            raise TypeError("effective output config must be serialized bytes")
        identity_bytes = canonical_json_bytes(dict(identity_payload)) + b"\n"
        effective_sha256 = hashlib.sha256(effective_output_bytes).hexdigest()
        identity_sha256 = hashlib.sha256(identity_bytes).hexdigest()
        if identity_payload.get("effective_output_config_sha256") != effective_sha256:
            raise ValueError("effective output config digest does not match its bytes")
        local_prepare = {
            "error": None,
            "effective_output_config_sha256": effective_sha256,
            "output_sampling_identity_sha256": identity_sha256,
        }
    except Exception as exc:  # noqa: BLE001 - synchronize local preparation before writing
        local_prepare = {"error": f"{type(exc).__name__}: {exc}"}

    preparations = comm.allgather(local_prepare)
    preparation_errors = []
    for rank, row in enumerate(preparations):
        if not isinstance(row, Mapping):
            preparation_errors.append(f"rank {rank}: invalid preparation record")
        elif row.get("error"):
            preparation_errors.append(f"rank {rank}: {row.get('error')}")
    if preparation_errors:
        raise ValueError(
            "Task42 output-probe receipt preparation refused: "
            + "; ".join(preparation_errors)
        )
    first_prepare = preparations[0]
    if any(row != first_prepare for row in preparations[1:]):
        raise ValueError("Task42 output-probe receipt inputs differ across MPI ranks")

    receipt = dict(identity_payload)
    receipt["output_sampling_identity_sha256"] = first_prepare[
        "output_sampling_identity_sha256"
    ]
    writer_status = None
    if comm.rank == 0:
        try:
            numerical_output.mkdir(parents=True, exist_ok=True)
            with effective_path.open("xb") as effective_file:
                effective_file.write(effective_output_bytes)
            with identity_path.open("xb") as identity_file:
                identity_file.write(identity_bytes)
            writer_status = {"error": None, "receipt": receipt}
        except Exception as exc:  # noqa: BLE001 - broadcast local O_EXCL/write failure
            writer_status = {"error": f"{type(exc).__name__}: {exc}", "receipt": None}

    writer_status = comm.bcast(writer_status, root=0)
    if not isinstance(writer_status, Mapping):
        raise TypeError("Task42 output-probe receipt writer returned no status")
    writer_error = writer_status.get("error")
    if writer_error:
        raise ValueError(f"Task42 output-probe receipt writer refused: {writer_error}")
    written_receipt = writer_status.get("receipt")
    if (
        not isinstance(written_receipt, Mapping)
        or written_receipt.get("output_sampling_identity_sha256")
        != first_prepare["output_sampling_identity_sha256"]
    ):
        raise ValueError("Task42 output-probe receipt writer returned an invalid receipt")
    return dict(written_receipt)


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
    task42_stage_gate=None,
    task42_bridge_path: str | Path | None = None,
    task42_packet_recovery_manifest: str | Path | None = None,
    task42_packet_recovery_manifest_sha256: str | None = None,
    task42_packet_recovery_archive_source_sha: str | None = None,
    task42_packet_recovery_archive_resolved_config_sha256: str | None = None,
    task42_packet_recovery_output_probes: Mapping[str, Any] | None = None,
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
    task42_lifecycle = (
        resolved_payload.get("model_id") == TASK42_13P5_FULL3D_MODEL_ID
        and lifecycle == TASK42_DIRECT_FACTOR_LIFECYCLE
    )
    task42_packet_recovery = task42_packet_recovery_manifest is not None
    if (task42_packet_recovery_manifest is None) != (
        task42_packet_recovery_manifest_sha256 is None
    ):
        raise ValueError("Task42 recovery manifest and SHA must be supplied together")
    if task42_lifecycle:
        if cfg.stage_case != "stage4_block_grating":
            raise ValueError("Task42 staged direct is limited to its Stage4 model")
        if not callable(task42_stage_gate):
            raise ValueError("Task42 staged direct requires the launcher phase gate")
        if task42_packet_recovery:
            if task42_bridge_path is not None:
                raise ValueError(
                    "Task42 packet recovery must not load the staged MUMPS bridge"
                )
            if source_sha is None or resolved_config_sha256 is None:
                raise ValueError("Task42 packet recovery requires RUN source bindings")
        elif not isinstance(task42_bridge_path, (str, Path)) or not str(
            task42_bridge_path
        ).strip():
            raise ValueError("Task42 staged direct requires an explicit bridge artifact")
    elif (
        task42_stage_gate is not None
        or task42_bridge_path is not None
        or task42_packet_recovery
        or task42_packet_recovery_output_probes is not None
    ):
        raise ValueError("Task42 stage gate/bridge arguments are not valid on other profiles")
    if task42_packet_recovery_output_probes is not None and not task42_packet_recovery:
        raise ValueError(
            "Task42 output-probe override is allowed only with a verified packet recovery"
        )
    if (
        task42_packet_recovery_archive_source_sha is not None
        and not task42_packet_recovery
    ):
        raise ValueError(
            "Task42 archive-source override is allowed only with a verified packet recovery"
        )
    if task42_packet_recovery_archive_source_sha is not None and (
        len(task42_packet_recovery_archive_source_sha) != 40
        or any(
            character not in "0123456789abcdef"
            for character in task42_packet_recovery_archive_source_sha
        )
    ):
        raise ValueError("Task42 archive source SHA must be 40 lowercase hex characters")
    if (
        task42_packet_recovery_archive_resolved_config_sha256 is not None
        and not task42_packet_recovery
    ):
        raise ValueError(
            "Task42 archive resolved-config SHA is allowed only with packet recovery"
        )
    if task42_packet_recovery_archive_resolved_config_sha256 is not None and (
        len(task42_packet_recovery_archive_resolved_config_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in task42_packet_recovery_archive_resolved_config_sha256
        )
    ):
        raise ValueError(
            "Task42 archive resolved-config SHA must be 64 lowercase hex characters"
        )
    if (
        task42_packet_recovery_output_probes is not None
        and task42_packet_recovery_archive_resolved_config_sha256 is None
    ):
        raise ValueError(
            "Task42 output-probe recovery requires the separately bound archive config SHA"
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
    elif lifecycle == TASK42_DIRECT_FACTOR_LIFECYCLE and task42_packet_recovery:
        # Recovery consumes the verified archived packet; it creates no new one.
        pass
    elif lifecycle == TASK42_DIRECT_FACTOR_LIFECYCLE:
        packet_directory = (
            Path(run_directory).resolve() / "numerical_output" / "pre_recovery_packet"
        )
        packet_identity = _task42_pre_recovery_packet_identity(
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
    recovery_identity: Mapping[str, Any] | None = None
    archive_probe_values_nm: Mapping[str, Any] | None = None
    if canonical_vector_export:
        runner_kwargs["solution_observer"] = solution_observer
    if packet_directory is not None:
        runner_kwargs.update(
            {
                "pre_recovery_packet_directory": packet_directory,
                "pre_recovery_packet_identity": packet_identity,
            }
        )
    if task42_lifecycle:
        runner_kwargs.update(
            {
                "task42_stage_gate": task42_stage_gate,
                "task42_bridge_path": (
                    None if task42_bridge_path is None else str(task42_bridge_path)
                ),
            }
        )
    if task42_packet_recovery:
        from mpi4py import MPI

        from src.solvers.full3d_lifecycle_packet import verify_task42_recovery_archive

        recovery_path = Path(task42_packet_recovery_manifest).resolve(strict=True)
        if not isinstance(source_sha, str) or len(source_sha) != 40:
            raise ValueError("Task42 packet recovery requires the complete current source SHA")
        archive_config_sha = (
            task42_packet_recovery_archive_resolved_config_sha256
            or resolved_config_sha256
        )
        if not isinstance(archive_config_sha, str) or len(archive_config_sha) != 64:
            raise ValueError(
                "Task42 packet recovery requires the archive resolved-config SHA"
            )
        allowed_source_shas = tuple(
            dict.fromkeys(
                value
                for value in (
                    TASK42_RECOVERY_ARCHIVE_SOURCE_SHA,
                    source_sha,
                    task42_packet_recovery_archive_source_sha,
                )
                if value is not None
            )
        )
        expected_identities = tuple(
            _task42_packet_recovery_expected_identity(
                resolved_payload,
                resolved_config_sha256=archive_config_sha,
                source_sha=archive_source_sha,
            )
            for archive_source_sha in allowed_source_shas
        )
        identity_bytes = json.dumps(
            expected_identities, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        identity_digest = hashlib.sha256(identity_bytes).hexdigest()
        comm = MPI.COMM_WORLD
        identity_digests = comm.allgather(identity_digest)
        if len(set(identity_digests)) != 1:
            raise ValueError("Task42 packet recovery identity differs across MPI ranks")
        archive_status = None
        if comm.rank == 0:
            try:
                receipt = verify_task42_recovery_archive(
                    recovery_path,
                    expected_manifest_sha256=str(
                        task42_packet_recovery_manifest_sha256
                    ),
                    expected_identity=expected_identities,
                    allowed_source_shas=allowed_source_shas,
                    expected_mpi_size=int(resolved_payload["execution"]["mpi_size"]),
                )
                archive_run_root = Path(str(receipt["run_root"]))
                archive_config_path = archive_run_root / "resolved_config.json"
                archive_config_bytes = archive_config_path.read_bytes()
                if hashlib.sha256(archive_config_bytes).hexdigest() != archive_config_sha:
                    raise ValueError(
                        "Task42 archive resolved-config file does not match its bound SHA"
                    )
                archive_payload = json.loads(archive_config_bytes)
                if not isinstance(archive_payload, Mapping):
                    raise TypeError("Task42 archive resolved config is not an object")
                archive_output = archive_payload.get("output")
                if not isinstance(archive_output, Mapping):
                    raise TypeError("Task42 archive output config is not an object")
                output_delta_errors = _task42_output_only_delta_errors(
                    archive_payload,
                    resolved_payload,
                    allow_probe_override=(
                        task42_packet_recovery_output_probes is not None
                    ),
                )
                if output_delta_errors:
                    raise ValueError(
                        "Task42 effective config differs outside the output-probe whitelist: "
                        + "; ".join(output_delta_errors)
                    )
                archive_status = {
                    "receipt": receipt,
                    "archive_probe_values_nm": {
                        "top_probe_z_nm": archive_output.get("top_probe_z_nm"),
                        "bottom_probe_z_nm": archive_output.get("bottom_probe_z_nm"),
                    },
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - root validation is broadcast before setup
                archive_status = {
                    "receipt": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        archive_status = comm.bcast(archive_status, root=0)
        if not isinstance(archive_status, Mapping) or archive_status.get("error"):
            detail = (
                "missing root archive validation receipt"
                if not isinstance(archive_status, Mapping)
                else archive_status.get("error")
            )
            raise ValueError(f"Task42 packet recovery archive rejected: {detail}")
        receipt = archive_status.get("receipt")
        archive_probe_values = archive_status.get("archive_probe_values_nm")
        if archive_probe_values is not None:
            if not isinstance(archive_probe_values, Mapping) or set(
                archive_probe_values
            ) != {"top_probe_z_nm", "bottom_probe_z_nm"}:
                raise ValueError("Task42 recovery archive probe identity is invalid")
            archive_probe_values_nm = dict(archive_probe_values)
        recovered_identity = (
            receipt.get("identity") if isinstance(receipt, Mapping) else None
        )
        if not isinstance(recovered_identity, Mapping):
            raise ValueError("Task42 packet recovery verifier returned no identity")
        recovery_identity = dict(recovered_identity)
        archive_run_root = Path(str(receipt["run_root"])).resolve(strict=True)
        runner_kwargs.update(
            {
                "task42_packet_recovery_manifest": recovery_path,
                "task42_packet_recovery_manifest_sha256": (
                    task42_packet_recovery_manifest_sha256
                ),
                "task42_packet_recovery_identity": recovery_identity,
            }
        )
    output_probe_override_receipt = None
    if task42_packet_recovery_output_probes is not None:
        if set(task42_packet_recovery_output_probes) != {
            "top_probe_z_nm",
            "bottom_probe_z_nm",
        }:
            raise ValueError(
                "Task42 recovery output override accepts only top/bottom probe coordinates"
            )
        top_probe = task42_packet_recovery_output_probes.get("top_probe_z_nm")
        bottom_probe = task42_packet_recovery_output_probes.get("bottom_probe_z_nm")
        if (
            resolved_payload.get("model_id") != TASK42_13P5_FULL3D_MODEL_ID
            or not _finite_number(top_probe)
            or not _finite_number(bottom_probe)
            or float(top_probe) != 125.0
            or float(bottom_probe) != -5.0
            or float(output.get("top_probe_z_nm", math.nan)) != float(top_probe)
            or float(output.get("bottom_probe_z_nm", math.nan)) != float(bottom_probe)
        ):
            raise ValueError(
                "Task42 recovery output override must match the effective resolved config and the registered 13.5 nm exterior probes 125/-5 nm"
            )
        # The archive has already passed its original input/resolved/physics/source
        # identity checks. These coordinates affect only postprocessing samples.
        cfg = replace(
            cfg,
            diffraction_top_probe_z=float(top_probe),
            diffraction_bottom_probe_z=float(bottom_probe),
        )
        from src.postprocessing.diffraction_3d import _probe_z_locations

        effective_top, effective_bottom = _probe_z_locations(cfg)
        if not isinstance(recovery_identity, Mapping):
            raise ValueError("Task42 output override has no verified archive identity")
        if not isinstance(archive_probe_values_nm, Mapping):
            raise ValueError("Task42 output override has no verified archived probe values")
        effective_output_payload = dict(resolved_payload)
        effective_output_payload["output"] = {
            **dict(output),
            "top_probe_z_nm": effective_top,
            "bottom_probe_z_nm": effective_bottom,
        }
        effective_output_bytes = canonical_json_bytes(effective_output_payload) + b"\n"
        effective_output_path = numerical_output / "effective_output_config.json"
        output_probe_override_receipt = {
            "schema": "task42.packet_recovery_output_probe_override.v1",
            "policy": "postprocess_only_after_original_archive_identity_pass",
            "archive_config_path": str(archive_run_root / "resolved_config.json"),
            "archive_source_sha": recovery_identity.get("source_sha"),
            "archive_input_sha256": recovery_identity.get("input_sha256"),
            "archive_resolved_config_sha256": recovery_identity.get(
                "resolved_config_sha256"
            ),
            "archive_physical_model_sha256": recovery_identity.get(
                "physical_model_sha256"
            ),
            "archive_probe_values_nm": dict(archive_probe_values_nm),
            "effective_probe_values_nm": {
                "top_probe_z_nm": effective_top,
                "bottom_probe_z_nm": effective_bottom,
            },
            "effective_output_config_path": str(effective_output_path),
            "effective_output_config_sha256": hashlib.sha256(
                effective_output_bytes
            ).hexdigest(),
            "effective_run_resolved_config_path": str(
                Path(run_directory).resolve() / "resolved_config.json"
            ),
            "effective_run_resolved_config_sha256": resolved_config_sha256,
            "output_sampling_identity_path": str(
                numerical_output / "output_sampling_identity.json"
            ),
            "physical_discretization_and_mode_identity_unchanged": True,
        }
        output_probe_override_receipt = _task42_write_output_probe_receipts(
            comm=comm,
            numerical_output=numerical_output,
            effective_output_bytes=effective_output_bytes,
            identity_payload=output_probe_override_receipt,
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
    if output_probe_override_receipt is not None:
        summary = dict(summary)
        summary["task42_packet_recovery_output_probe_override"] = (
            output_probe_override_receipt
        )
    errors = (
        _stage4_authority_errors(
            summary, residual_limit=5.0e-9 if task42_lifecycle else 1.0e-9
        )
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
