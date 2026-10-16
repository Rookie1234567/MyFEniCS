"""Task41's first explicitly registered 3D physical case.

This small identity contract keeps the new phi=90, 50-by-50 nm geometry
separate from the paused Task40 cases while continuing to use the shared
Full3D mesh, mode, assembly, and solve code.
"""

from __future__ import annotations

import math
import json
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np


TASK41_MODEL_ID = "task41extra_phi90_p50x50_g17x20"
TASK41_COMPARISON_GROUP = "task41extra_phi90_p50x50_g17x20_g13_a1a2"
TASK41_G13_A1_RUN_ID = "task41extra_g13_p6_phi90_direct_a1"
TASK41_G13_A2_RUN_ID = "task41extra_g13_p6_phi90_iterative_a2"
TASK41_G13_A2_INPUT_RELATIVE = (
    "input/task41extra_phi90_p50x50_g17x20/g13_p6_iterative_a2.dat"
)
TASK41_G13_A2_PRECONDITIONER = (
    "task41extra_g13_p6_phi90_a2_y_orbit_reference_v1"
)
TASK41_G13_GEOMETRY_IDENTITY = "task41extra_g13_rectangular_no_void"
TASK41_MUMPS_EXACT_ICNTL = {2: 0, 3: 6, 4: 2, 10: 0, 22: 0, 35: 0}

TASK41_SI_INDEX_BY_WAVELENGTH_NM = {
    13.5: (0.999002304859, 0.00182649365),
    0.7: (0.99988517036884961, 4.3236152269189515e-6),
}

TASK41_G13_X_AXIS_NM = (
    0.0,
    5.5,
    11.0,
    16.5,
    20.75,
    25.0,
    29.25,
    33.5,
    39.0,
    44.5,
    50.0,
)
TASK41_G13_Y_AXIS_NM = tuple(float(value) for value in range(0, 51, 5))
TASK41_G13_Z_AXIS_NM = (-10.0, *tuple(float(value) for value in range(0, 121, 10)), 130.0)
TASK41_G13_CELL_COUNTS = (10, 10, 14)


def is_task41_geometry_identity(identity: Any) -> bool:
    return identity == TASK41_G13_GEOMETRY_IDENTITY


def task41_incident_eh_fields(cfg: Any) -> dict[str, Any]:
    """Return the incident vectors with the project's physical field units."""

    from src.common.modes_3d import mode_eh_vectors

    k_vector, _unit_e, h_code = mode_eh_vectors(
        cfg.kx,
        cfg.ky,
        abs(cfg.kz),
        cfg.polarization_vector,
        -1,
        cfg,
    )
    e_si = (
        cfg.incident_amplitude
        * cfg.electric_field_scale_V_per_m
        * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    )
    h_si = (
        cfg.incident_amplitude
        * cfg.magnetic_field_scale_A_per_m
        * np.asarray(h_code, dtype=np.complex128)
    )

    def pairs(values: Any) -> list[list[float]]:
        return [[float(value.real), float(value.imag)] for value in values]

    return {
        "incident_wavevector_nm_inverse": pairs(k_vector),
        "incident_electric_field_V_per_m": pairs(e_si),
        "incident_magnetic_field_A_per_m": pairs(h_si),
    }


def task41_payload_errors(payload: Mapping[str, Any]) -> list[str]:
    """Fail closed for Task41 inputs while leaving all other models untouched."""

    if payload.get("model_id") != TASK41_MODEL_ID:
        return []

    errors: list[str] = []
    run_id = payload.get("run_id")
    is_a1 = run_id == TASK41_G13_A1_RUN_ID
    is_a2 = run_id == TASK41_G13_A2_RUN_ID
    case_label = "A1" if is_a1 else "A2"

    def section(name: str) -> Mapping[str, Any]:
        value = payload.get(name)
        if not isinstance(value, Mapping):
            errors.append(f"{name} payload is missing")
            return {}
        return value

    def check(section_name: str, values: Mapping[str, Any]) -> None:
        actual_section = section(section_name)
        for key, expected in values.items():
            actual = actual_section.get(key)
            if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                if not isinstance(actual, (int, float)) or isinstance(actual, bool) or not math.isclose(
                    float(actual), float(expected), rel_tol=0.0, abs_tol=1.0e-12
                ):
                    errors.append(
                        f"{section_name}.{key} does not match Task41 G13 {case_label}"
                    )
            elif actual != expected:
                errors.append(
                    f"{section_name}.{key} does not match Task41 G13 {case_label}"
                )

    if not (is_a1 or is_a2):
        errors.append("run_id is not a registered Task41 case")
    if payload.get("comparison_group") != TASK41_COMPARISON_GROUP:
        errors.append("comparison_group does not match Task41 G13 A1/A2")
    if payload.get("dimension") != 3:
        errors.append("Task41 G13 A1/A2 requires dimension=3")

    check(
        "geometry",
        {
            "geometry_kind": "rectangular_block_grating",
            "geometry_identity": TASK41_G13_GEOMETRY_IDENTITY,
            "period_x_nm": 50.0,
            "period_y_nm": 50.0,
            "z_min_nm": -10.0,
            "z_max_nm": 130.0,
            "interface_z_nm": 0.0,
            "air_height_nm": 130.0,
            "substrate_thickness_nm": 10.0,
            "grating_width_x_nm": 17.0,
            "grating_width_y_nm": 20.0,
            "grating_height_nm": 120.0,
        },
    )
    geometry = section("geometry")
    if geometry.get("air_void_box_nm") is not None or geometry.get("cell_notch") is not None:
        errors.append(f"Task41 G13 {case_label} must not contain a void or notch")

    check(
        "materials",
        {
            "n_air": [1.0, 0.0],
            "n_substrate": list(TASK41_SI_INDEX_BY_WAVELENGTH_NM[13.5]),
            "n_grating": list(TASK41_SI_INDEX_BY_WAVELENGTH_NM[13.5]),
        },
    )
    check(
        "incidence",
        {
            "wavelength_nm": 13.5,
            "grazing_angle_deg": 1.0,
            "azimuth_deg": 90.0,
            "polarization": "s",
            "electric_amplitude": 1.0,
        },
    )
    check(
        "discretization",
        {
            "nedelec_degree": 6,
            "mesh_cell_type": "hexahedron",
            "mesh_spacing_mode": "boundary_fitted",
            "assembly_backend": "assembly_time_static_condensed",
            "mesh_axis_cell_counts": list(TASK41_G13_CELL_COUNTS),
            "mesh_axis_x_values": list(TASK41_G13_X_AXIS_NM),
            "mesh_axis_y_values": list(TASK41_G13_Y_AXIS_NM),
            "mesh_axis_z_values": list(TASK41_G13_Z_AXIS_NM),
            "mesh_axis_z_profile": "task41_g13_z_minus10_0_120_130",
        },
    )
    check(
        "boundary",
        {
            "use_floquet_x": True,
            "use_floquet_y": True,
            "vertical_boundary": "dtn_port",
            "dtn_order_policy": "auto_propagating",
            "dtn_assembly": "auxiliary",
            "use_pml": False,
        },
    )
    if is_a1:
        check("method", {"kind": "full3d_direct"})
        check(
            "solver",
            {"linear_solver": "direct", "direct_solver_profile": "mumps_exact"},
        )
    elif is_a2:
        check("method", {"kind": "full3d_iterative"})
        check(
            "solver",
            {
                "linear_solver": "iterative",
                "ksp_type": "fgmres",
                "preconditioner": TASK41_G13_A2_PRECONDITIONER,
                "stage": "TASK41_A2",
                "initial_guess": "zero",
                "restart": 32,
                "max_iterations": 2048,
                "memory_policy": "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
                "outer_restart": 0,
                "physical_operator_backend": "isotropic_sum_factorized_n1e_v26",
                "h6_backend_rule": "direct_selected_backend_same_apply_and_power10",
                "thread_contract": "mpi1_omp1_blas1_v26",
                "task40_reference_pc_strategy": (
                    "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
                ),
                "task40_q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
                "task40_factor_lifecycle_strategy": "ALL_Q_RESIDENT",
            },
        )
    check(
        "output",
        {
            "export_fields": True,
            "export_diffraction_orders": True,
            "export_canonical_vectors": True,
            "export_modal_amplitudes": True,
            "export_reference_planes": True,
            "diffraction_order_max_m": 8,
            "diffraction_order_max_n": 8,
            "top_probe_z_nm": 125.0,
            "bottom_probe_z_nm": -5.0,
        },
    )
    check(
        "execution",
        {
            "warning_memory_gib": 1228.8,
            "terminate_memory_gib": 1536.0,
            "timeout_seconds": 172800,
            "require_zero_swap": True,
        },
    )
    if is_a2:
        check("execution", {"memory_limit_gb": 1536.0})
    if errors:
        return errors
    return []


def task41_direct_summary_errors(
    summary: Mapping[str, Any],
    numerical_output_directory: str | Path | None = None,
) -> list[str]:
    """Recheck native full-space A6, full-field recovery, and energy gates.

    The checker reads rank-local RHS, residual, and recovered-field arrays
    emitted by the independent full FE plus DtN action, then recomputes their
    norms and hashes. It separately recomputes regional volume absorption and
    energy closure from the saved power outputs.
    """

    errors: list[str] = []
    if summary.get("case_status") != "completed":
        errors.append("Task41 direct case_status is not completed")
    if summary.get("official_result") is not True:
        errors.append("Task41 direct official_result is not true")
    if summary.get("actual_pc_factor_solver_type") != "mumps":
        errors.append("Task41 direct factor solver was not read back as MUMPS")
    if summary.get("petsc_direct_solver_profile") != "mumps_exact":
        errors.append("Task41 direct solver profile was not mumps_exact")
    if summary.get("stage4_full3d_assembly_backend_actual") != "assembly_time_static_condensed":
        errors.append("Task41 direct solve did not read back static-condensed assembly")
    if summary.get("stage4_assembly_time_cell_static_condensation") is not True:
        errors.append("Task41 direct solve did not confirm assembly-time condensation")
    if summary.get("stage4_floquet_slave_elimination") is not True:
        errors.append("Task41 direct solve did not confirm Floquet slave elimination")
    if summary.get("task41_native_a6_gate_pass") is not True:
        errors.append("Task41 native full A6 gate did not pass before official R/T/A")
    if summary.get("official_rta_gate_pass") is not True:
        errors.append("Task41 official R/T/A gate did not pass")
    readback = summary.get("mumps_control_readback")
    if not isinstance(readback, Mapping):
        errors.append("Task41 direct summary lacks MUMPS ICNTL readback")
    else:
        observed = readback.get("observed_icntl")
        if not isinstance(observed, Mapping):
            errors.append("Task41 direct MUMPS ICNTL readback is missing")
        else:
            for index, expected in TASK41_MUMPS_EXACT_ICNTL.items():
                if observed.get(str(index)) != expected:
                    errors.append(f"Task41 MUMPS ICNTL({index}) readback mismatch")
        if readback.get("pass") is not True:
            errors.append("Task41 MUMPS control readback did not pass")

    def finite_nonnegative(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0.0
        )

    def finite_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    def close(left: Any, right: Any, *, tolerance: float = 1.0e-12) -> bool:
        return (
            isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
            and math.isfinite(float(left))
            and math.isfinite(float(right))
            and math.isclose(
                float(left), float(right), rel_tol=tolerance, abs_tol=tolerance
            )
        )

    condensation = summary.get("cell_static_condensation")
    if not isinstance(condensation, Mapping):
        errors.append("Task41 direct summary lacks the full-field recovery audit")
        condensation = {}

    recovery = condensation.get("recovery")
    if not isinstance(recovery, Mapping):
        errors.append("Task41 direct summary lacks full-field recovery evidence")
    else:
        if recovery.get("status") != "full_field_recovered_without_full_global_matrix":
            errors.append("Task41 full-field recovery did not complete")
        if not finite_nonnegative(recovery.get("recovered_interior_rows")) or int(
            recovery.get("recovered_interior_rows", 0)
        ) <= 0:
            errors.append("Task41 full-field recovery did not restore interior rows")
        if recovery.get("full_global_matrix_allocated") is not False:
            errors.append("Task41 recovery audit does not match the matrix-free path")

    if numerical_output_directory is None:
        errors.append("Task41 independent power outputs were not provided to the checker")
        return errors

    output_directory = Path(numerical_output_directory)

    def read_object(filename: str) -> Mapping[str, Any] | None:
        try:
            value = json.loads((output_directory / filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"Task41 independent output {filename} is missing or invalid")
            return None
        if not isinstance(value, Mapping):
            errors.append(f"Task41 independent output {filename} is not an object")
            return None
        return value

    def verify_stage_record(summary_key: str, filename: str) -> Mapping[str, Any] | None:
        summary_record = summary.get(summary_key)
        if not isinstance(summary_record, Mapping):
            errors.append(f"Task41 summary lacks {summary_key} evidence")
            return None
        artifact = read_object(filename)
        if artifact is None:
            return None
        hashed = dict(artifact)
        saved_digest = hashed.pop("record_sha256", None)
        canonical = json.dumps(
            hashed, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        actual_digest = hashlib.sha256(canonical).hexdigest()
        if (
            saved_digest != actual_digest
            or summary_record.get("record_sha256") != actual_digest
            or summary_record.get("artifact_file") != filename
        ):
            errors.append(f"Task41 {summary_key} artifact identity hash mismatch")
        try:
            normalized_summary_record = json.loads(
                json.dumps(summary_record, allow_nan=False)
            )
        except (TypeError, ValueError):
            normalized_summary_record = {}
            errors.append(f"Task41 {summary_key} summary record is not JSON-safe")
        for key, value in hashed.items():
            if normalized_summary_record.get(key) != value:
                errors.append(f"Task41 {summary_key} field {key} differs from artifact")
        return hashed

    admission = verify_stage_record(
        "task41_mumps_symbolic_admission",
        "task41_mumps_symbolic_admission.json",
    )
    if admission is not None:
        info = admission.get("symbolic_info")
        infog = info.get("infog") if isinstance(info, Mapping) else None
        expected_icntl = {str(key): value for key, value in TASK41_MUMPS_EXACT_ICNTL.items()}
        post_resource = admission.get("post_release_resource")
        post_tree = (
            post_resource.get("process_tree")
            if isinstance(post_resource, Mapping)
            else None
        )
        post_envelope = admission.get("post_release_memory_envelope")
        if admission.get("schema") != "task41.mumps_symbolic_admission.v1":
            errors.append("Task41 symbolic admission schema is invalid")
        if admission.get("status") != "ADMISSIBLE":
            errors.append("Task41 symbolic MUMPS resource gate did not admit numeric")
        if admission.get("numeric_called") is not False:
            errors.append("Task41 symbolic admission record claims numeric was already called")
        if admission.get("symbolic_calls") != 1:
            errors.append("Task41 MUMPS symbolic probe did not run exactly once")
        if admission.get("probe_factor_released_before_ksp_setup") is not True:
            errors.append("Task41 symbolic probe factor was not released before numeric setup")
        if admission.get("final_admission_sample_after_probe_release") is not True:
            errors.append("Task41 final resource sample was not taken after probe release")
        if admission.get("exact_icntl_expected") != expected_icntl or admission.get(
            "symbolic_probe_control_readback"
        ) != expected_icntl:
            errors.append("Task41 symbolic probe MUMPS controls differ from the exact profile")
        if not isinstance(infog, Mapping) or any(
            not isinstance(infog.get(str(index)), int)
            or isinstance(infog.get(str(index)), bool)
            or int(infog[str(index)]) <= 0
            for index in (16, 17)
        ):
            errors.append("Task41 symbolic MUMPS INFOG(16/17) estimates are missing")
        if not isinstance(post_resource, Mapping) or post_resource.get(
            "job_no_swap"
        ) is not True:
            errors.append("Task41 post-release resource sample did not confirm zero swap")
        if not isinstance(post_tree, Mapping) or (
            post_tree.get("all_status_readable") is not True
            or post_tree.get("swap_bytes") != 0
        ):
            errors.append("Task41 post-release process-tree resource evidence is invalid")
        if (
            not isinstance(post_envelope, Mapping)
            or post_envelope.get("memory_policy")
            != "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
            or not isinstance(post_envelope.get("cgroup_limits"), list)
            or not isinstance(post_envelope.get("launch_cap_bytes"), int)
            or not isinstance(post_envelope.get("reserve_bytes"), int)
            or post_envelope.get("reserve_bytes", 0) < 64 * 1024**3
        ):
            errors.append("Task41 ancestor-aware memory envelope or 64 GiB reserve is invalid")
        if admission.get("decision_errors") != []:
            errors.append("Task41 symbolic MUMPS admission retained decision errors")

    numeric_stage = verify_stage_record(
        "task41_mumps_numeric_stage", "task41_mumps_numeric_stage.json"
    )
    if numeric_stage is not None:
        readback = numeric_stage.get("mumps_control_readback")
        factor_inventory = numeric_stage.get("factor_inventory_after_setup")
        release_resource = numeric_stage.get("resource_after_factor_release")
        release_tree = (
            release_resource.get("process_tree")
            if isinstance(release_resource, Mapping)
            else None
        )
        release_envelope = numeric_stage.get("memory_envelope_after_factor_release")
        raw_infog = (
            factor_inventory.get("mumps_raw_infog")
            if isinstance(factor_inventory, Mapping)
            else None
        )
        if (
            numeric_stage.get("schema") != "task41.mumps_numeric_stage.v1"
            or numeric_stage.get("status") != "COMPLETED"
            or numeric_stage.get("numeric_called") is not True
            or numeric_stage.get("numeric_completed") is not True
            or numeric_stage.get("ksp_setup_repeats_symbolic_before_numeric") is not True
            or numeric_stage.get("actual_pc_factor_solver_type") != "mumps"
            or numeric_stage.get("factor_released_before_native_a6") is not True
            or numeric_stage.get("ksp_destroy_called") is not True
            or numeric_stage.get("pc_python_reference_deleted_before_ksp_destroy")
            is not True
            or numeric_stage.get("petsc_garbage_cleanup_called") is not True
        ):
            errors.append("Task41 actual MUMPS numeric stage did not complete as contracted")
        if (
            not isinstance(release_resource, Mapping)
            or release_resource.get("job_no_swap") is not True
            or not isinstance(release_tree, Mapping)
            or release_tree.get("all_status_readable") is not True
            or release_tree.get("swap_bytes") != 0
            or not isinstance(release_envelope, Mapping)
            or release_envelope.get("memory_policy")
            != "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
            or not isinstance(release_envelope.get("cgroup_limits"), list)
            or not isinstance(release_envelope.get("launch_cap_bytes"), int)
            or release_envelope.get("reserve_bytes", 0) < 64 * 1024**3
        ):
            errors.append("Task41 factor-release resource sample or ancestor envelope is invalid")
        if not isinstance(readback, Mapping) or readback.get("pass") is not True:
            errors.append("Task41 actual MUMPS numeric-stage ICNTL readback failed")
        elif readback.get("observed_icntl") != {
            str(index): value for index, value in TASK41_MUMPS_EXACT_ICNTL.items()
        }:
            errors.append("Task41 numeric-stage MUMPS controls differ from exact profile")
        if (
            not isinstance(factor_inventory, Mapping)
            or factor_inventory.get("factor_solver_type") != "mumps"
            or factor_inventory.get("mumps_api_available") is not True
            or not isinstance(raw_infog, Mapping)
            or "1" not in raw_infog
        ):
            errors.append("Task41 numeric-stage raw MUMPS INFOG readback is incomplete")
        if (
            admission is not None
            and numeric_stage.get("symbolic_admission_record_sha256")
            != summary["task41_mumps_symbolic_admission"].get("record_sha256")
        ):
            errors.append("Task41 MUMPS numeric stage is not bound to symbolic admission")

    native = summary.get("task41_native_full_a6")
    if not isinstance(native, Mapping):
        errors.append("Task41 summary lacks the native full A6 action evidence")
        native = {}
    native_file = read_object("task41_native_full_a6_residual.json")
    if native_file is not None:
        hashed_record = dict(native_file)
        saved_digest = hashed_record.pop("record_sha256", None)
        canonical = json.dumps(
            hashed_record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        actual_digest = hashlib.sha256(canonical).hexdigest()
        if saved_digest != actual_digest or native.get("record_sha256") != actual_digest:
            errors.append("Task41 native full A6 artifact identity hash mismatch")
        if native.get("artifact_file") != "task41_native_full_a6_residual.json":
            errors.append("Task41 summary does not identify the native full A6 artifact")
        for key, value in hashed_record.items():
            if native.get(key) != value:
                errors.append(f"Task41 summary native full A6 field {key} differs from artifact")
        if (
            hashed_record.get("schema") != "task41.native_full_a6_residual.v1"
            or hashed_record.get("operator") != "A_volume_plus_dynamic_DtN"
            or hashed_record.get("fullspace_mpc_volume_action") is not True
            or hashed_record.get("fullspace_dtn_action") is not True
            or hashed_record.get("field_representation")
            != "recovered_physical_fe_field_after_mpc_backsubstitution"
            or hashed_record.get("action_input_representation")
            != "recovered_field_copy_with_owned_mpc_slave_entries_zeroed"
            or hashed_record.get("action_input_mpc_slave_entries_zeroed") is not True
            or hashed_record.get("mumps_factor_released_before_native_a6") is not True
            or not isinstance(summary.get("task41_mumps_numeric_stage"), Mapping)
            or hashed_record.get("mumps_factor_release_record_sha256")
            != summary["task41_mumps_numeric_stage"].get("record_sha256")
        ):
            errors.append("Task41 native full A6 evidence has an invalid operator identity")

        mpi_size = hashed_record.get("mpi_size")
        rank_records = hashed_record.get("rank_local_records")
        if (
            not finite_nonnegative(mpi_size)
            or int(mpi_size) <= 0
            or not isinstance(rank_records, list)
            or len(rank_records) != int(mpi_size)
        ):
            errors.append("Task41 native full A6 rank records are incomplete")
        else:
            ranks: list[int] = []
            rhs_sq: list[float] = []
            residual_sq: list[float] = []
            max_abs: list[float] = []
            owned_counts: list[int] = []
            for row in rank_records:
                if not isinstance(row, Mapping):
                    errors.append("Task41 native full A6 rank record is malformed")
                    continue
                rank = row.get("rank")
                owned = row.get("owned_dof_count")
                if (
                    not finite_nonnegative(rank)
                    or int(rank) != rank
                    or not finite_nonnegative(owned)
                    or int(owned) != owned
                    or not finite_nonnegative(row.get("rhs_norm_squared"))
                    or not finite_nonnegative(row.get("residual_norm_squared"))
                    or not finite_nonnegative(row.get("residual_max_abs"))
                ):
                    errors.append("Task41 native full A6 rank record has invalid values")
                    continue
                ranks.append(int(rank))
                owned_counts.append(int(owned))
                rhs_sq.append(float(row["rhs_norm_squared"]))
                residual_sq.append(float(row["residual_norm_squared"]))
                max_abs.append(float(row["residual_max_abs"]))
                artifact_name = row.get("rank_artifact_file")
                if (
                    not isinstance(artifact_name, str)
                    or Path(artifact_name).name != artifact_name
                ):
                    errors.append("Task41 native full A6 rank artifact path is invalid")
                    continue
                rank_path = output_directory / artifact_name
                rank_digest = hashlib.sha256()
                try:
                    artifact_size = rank_path.stat().st_size
                    with rank_path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                            rank_digest.update(chunk)
                    if rank_digest.hexdigest() != row.get("rank_artifact_sha256"):
                        errors.append(f"Task41 native full A6 rank {rank} artifact hash mismatch")
                    if artifact_size != row.get("rank_artifact_bytes"):
                        errors.append(f"Task41 native full A6 rank {rank} artifact size mismatch")
                    vector_bytes = row.get("vector_bytes_local")
                    action_bytes = row.get("action_bytes_local")
                    if (
                        not isinstance(vector_bytes, Mapping)
                        or not isinstance(action_bytes, Mapping)
                        or not all(finite_nonnegative(value) for value in vector_bytes.values())
                        or not all(finite_nonnegative(value) for value in action_bytes.values())
                        or sum(int(value) for value in vector_bytes.values())
                        + sum(int(value) for value in action_bytes.values())
                        != row.get("tracked_workspace_bytes_local")
                    ):
                        errors.append(f"Task41 native full A6 rank {rank} workspace accounting is invalid")
                    with np.load(rank_path, allow_pickle=False) as arrays:
                        rhs_values = np.asarray(arrays["rhs"])
                        residual_values = np.asarray(arrays["residual"])
                        recovered_values = np.asarray(arrays["recovered_field"])
                        slave_rows = np.asarray(arrays["mpc_slave_local_rows"])
                    if any(
                        values.dtype != np.dtype(np.complex128)
                        or values.shape != (int(owned),)
                        or not np.isfinite(values).all()
                        for values in (rhs_values, residual_values, recovered_values)
                    ):
                        errors.append(f"Task41 native full A6 rank {rank} vectors are invalid")
                    else:
                        if not close(
                            row["rhs_norm_squared"],
                            float(np.vdot(rhs_values, rhs_values).real),
                            tolerance=1.0e-10,
                        ):
                            errors.append(f"Task41 native full A6 rank {rank} RHS norm differs from raw vector")
                        if not close(
                            row["residual_norm_squared"],
                            float(np.vdot(residual_values, residual_values).real),
                            tolerance=1.0e-10,
                        ):
                            errors.append(f"Task41 native full A6 rank {rank} residual norm differs from raw vector")
                        if not close(
                            row["residual_max_abs"],
                            float(np.max(np.abs(residual_values), initial=0.0)),
                            tolerance=1.0e-10,
                        ):
                            errors.append(f"Task41 native full A6 rank {rank} maximum differs from raw vector")
                        field_digest = hashlib.sha256(
                            np.ascontiguousarray(recovered_values, dtype="<c16").view(
                                np.uint8
                            )
                        ).hexdigest()
                        if field_digest != row.get("recovered_field_sha256"):
                            errors.append(f"Task41 rank {rank} recovered field hash mismatch")
                        if (
                            slave_rows.dtype.kind not in "iu"
                            or slave_rows.ndim != 1
                            or np.any(slave_rows < 0)
                            or np.any(slave_rows >= int(owned))
                            or np.unique(slave_rows).size != slave_rows.size
                        ):
                            errors.append(f"Task41 rank {rank} MPC slave row list is invalid")
                except (OSError, ValueError, KeyError, EOFError):
                    errors.append(f"Task41 native full A6 rank {rank} raw vector artifact is unreadable")
            if sorted(ranks) != list(range(int(mpi_size))):
                errors.append("Task41 native full A6 rank inventory does not close")
            if len(rhs_sq) == len(rank_records) and len(residual_sq) == len(rank_records):
                recomputed_rhs = math.sqrt(sum(rhs_sq))
                recomputed_residual = math.sqrt(sum(residual_sq))
                recomputed_relative = recomputed_residual / max(recomputed_rhs, 1.0e-30)
                if sum(owned_counts) != hashed_record.get("global_dof_count"):
                    errors.append("Task41 native full A6 owned-row counts do not close")
                if hashed_record.get("global_dof_count") != summary.get(
                    "num_nedelec_dofs"
                ):
                    errors.append("Task41 native full A6 row count differs from the FE space")
                if not close(hashed_record.get("rhs_norm"), recomputed_rhs):
                    errors.append("Task41 native full A6 RHS norm does not recompute")
                if not close(hashed_record.get("residual_norm"), recomputed_residual):
                    errors.append("Task41 native full A6 residual norm does not recompute")
                if not close(hashed_record.get("relative_residual"), recomputed_relative):
                    errors.append("Task41 native full A6 relative residual does not recompute")
                if not close(
                    hashed_record.get("residual_max_abs"), max(max_abs, default=0.0)
                ):
                    errors.append("Task41 native full A6 maximum residual does not recompute")
                if recomputed_relative > 1.0e-6:
                    errors.append("Task41 native full A6 relative residual exceeds 1e-6")
                if summary.get("task41_native_a6_gate_pass") is not (
                    recomputed_relative <= 1.0e-6
                ):
                    errors.append("Task41 native A6 gate status differs from raw-vector recomputation")
        mode_hash = hashed_record.get("mode_manifest_sha256")
        if (
            not isinstance(mode_hash, str)
            or len(mode_hash) != 64
            or any(character not in "0123456789abcdef" for character in mode_hash)
        ):
            errors.append("Task41 native full A6 mode manifest identity is invalid")

    volume = read_object("volume_absorption.json")
    port = read_object("port_power.json")
    if volume is None or port is None:
        return errors
    if (
        volume.get("method") != "volume_absorption"
        or volume.get("role") != "absorption_check"
        or volume.get("status") != "ok"
        or volume.get("field_model_for_absorption") != "total_field"
        or volume.get("power_source") != "volume_integral_Im_epsilon_E2"
        or volume.get("pml_cells_excluded") is not True
        or volume.get("air_cells_excluded") is not True
    ):
        errors.append("Task41 A_volume output is not an independent total-field material integral")
    incident_power = volume.get("incident_power_code_units")
    if not finite_nonnegative(incident_power) or float(incident_power) <= 0.0:
        errors.append("Task41 A_volume output has invalid incident-power normalization")
        incident_power = None
    regions = volume.get("regions")
    if not isinstance(regions, Mapping):
        errors.append("Task41 A_volume output lacks regional raw power records")
        regions = {}
    recomputed_region_a: dict[str, float] = {}
    for region_name in ("grating", "substrate"):
        region = regions.get(region_name)
        if not isinstance(region, Mapping):
            errors.append(f"Task41 A_volume output lacks the {region_name} region")
            continue
        absorbed = region.get("absorbed_power_code_units")
        ratio = region.get("A_volume")
        if (
            region.get("status") != "ok"
            or not finite_nonnegative(absorbed)
            or not finite_nonnegative(ratio)
            or not finite_nonnegative(region.get("cell_count"))
            or int(region.get("cell_count", 0)) <= 0
            or not finite_nonnegative(region.get("volume_nm3"))
            or float(region.get("volume_nm3", 0.0)) <= 0.0
            or not finite_nonnegative(region.get("Im_epsilon_r"))
            or float(region.get("Im_epsilon_r", 0.0)) <= 0.0
        ):
            errors.append(f"Task41 A_volume {region_name} raw integral is incomplete")
            continue
        if incident_power is not None and not close(
            ratio, float(absorbed) / float(incident_power)
        ):
            errors.append(f"Task41 A_volume {region_name} normalization does not recompute")
        recomputed_region_a[region_name] = float(ratio)
    if len(recomputed_region_a) == 2:
        recomputed_a_volume = sum(recomputed_region_a.values())
        if not close(volume.get("A_grating"), recomputed_region_a["grating"]):
            errors.append("Task41 A_volume grating aggregate differs from its raw integral")
        if not close(volume.get("A_substrate"), recomputed_region_a["substrate"]):
            errors.append("Task41 A_volume substrate aggregate differs from its raw integral")
        if not close(volume.get("A_volume_total"), recomputed_a_volume):
            errors.append("Task41 independent A_volume total does not recompute")
    else:
        recomputed_a_volume = math.nan

    if (
        port.get("method") != "port"
        or port.get("role") != "primary"
        or port.get("status") != "ok"
        or port.get("power_source") != "dtn_port_modal_amplitudes"
    ):
        errors.append("Task41 port output is not the completed primary modal result")
    port_r = port.get("R_total")
    port_t = port.get("T_total")
    port_a = port.get("A_balance")
    if not all(finite_nonnegative(value) for value in (port_r, port_t)) or not finite_number(
        port_a
    ):
        errors.append("Task41 primary port output lacks finite R/T/A_balance")
    elif not close(port_a, 1.0 - float(port_r) - float(port_t)):
        errors.append("Task41 port A_balance does not recompute from R and T")

    orders = port.get("orders")
    if (
        not isinstance(orders, list)
        or not finite_nonnegative(native_file.get("mode_count") if native_file else None)
        or len(orders) != int(native_file.get("mode_count", -1))
    ):
        errors.append("Task41 native A6 modes do not match the saved complete port inventory")

    summary_values = {
        "R_total": port_r,
        "T_total": port_t,
        "A_volume_total": recomputed_a_volume,
    }
    if all(finite_nonnegative(value) for value in summary_values.values()) and finite_number(
        port_a
    ):
        for name, expected in summary_values.items():
            if not close(summary.get(name), expected):
                errors.append(f"Task41 summary {name} differs from independent output")
        if not close(summary.get("A_balance"), port_a):
            errors.append("Task41 summary A_balance differs from independent output")
        closure = float(port_r) + float(port_t) + float(recomputed_a_volume) - 1.0
        absorption_gap = float(port_a) - float(recomputed_a_volume)
        if abs(closure) > 1.0e-5:
            errors.append("Task41 independent R+T+A_volume energy error exceeds 1e-5")
        if abs(absorption_gap) > 1.0e-5:
            errors.append("Task41 independent A_balance-A_volume error exceeds 1e-5")
        if not close(summary.get("energy_closure_error_port_volume"), closure):
            errors.append("Task41 saved port-volume energy error does not recompute")
        if not close(summary.get("A_port_balance_minus_A_volume_total"), absorption_gap):
            errors.append("Task41 saved A_balance-A_volume difference does not recompute")
    return errors


__all__ = [
    "TASK41_COMPARISON_GROUP",
    "TASK41_G13_A1_RUN_ID",
    "TASK41_G13_CELL_COUNTS",
    "TASK41_G13_GEOMETRY_IDENTITY",
    "TASK41_G13_X_AXIS_NM",
    "TASK41_G13_Y_AXIS_NM",
    "TASK41_G13_Z_AXIS_NM",
    "TASK41_MODEL_ID",
    "TASK41_MUMPS_EXACT_ICNTL",
    "TASK41_SI_INDEX_BY_WAVELENGTH_NM",
    "is_task41_geometry_identity",
    "task41_incident_eh_fields",
    "task41_direct_summary_errors",
    "task41_payload_errors",
]
