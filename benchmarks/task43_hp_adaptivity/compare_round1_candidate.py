"""Compare one solved Task43 round-one candidate on the frozen shared G rule."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from dolfinx import fem
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity import compare_initial_to_references as base
from benchmarks.task43_hp_adaptivity.candidate_records import (
    load_accepted_parent_artifacts,
)
from benchmarks.task43_hp_adaptivity.h100_anchor import (
    _assert_mesh_profile,
    _h100_config,
    _sha256_file,
    _validate_round1_candidate_inputs,
)
from src.adaptivity.physical_g_error import (
    accumulate_physical_g_cell_contributions,
    dorfler_mark_physical_g,
)
from src.adaptivity.stage4_local_h import build_stage4_local_h_mesh_data
from src.postprocessing.physical_field_comparison import build_common_volume_quadrature
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.solvers.common_3d_solve import _create_nedelec_space

ROOT = Path(__file__).resolve().parents[2]
CURRENT_RUN = ROOT / "benchmarks/artifacts/task43/current_180/attempt1/run"
REFERENCE_ROOT = ROOT / "benchmarks/artifacts/task43/reference_imports/attempt2"
REFERENCE_COMPARISON = ROOT / "benchmarks/artifacts/task43/reference_comparison/attempt2"
ACCEPTANCE = ROOT / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
COMPARISON_CONTRACT = ROOT / "docs/task43_hp_adaptivity/outcomes/records/comparison_contract_v1.json"
CANDIDATE_RECORDS = Path(__file__).with_name("candidate_records.py")
DEFAULT_OUTPUT = ROOT / "benchmarks/artifacts/task43/round1_candidates/comparisons"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return digest.hexdigest()


def _load_modal_case(label: str) -> dict[str, Any]:
    if label == "current_180":
        record_path = CURRENT_RUN / "task43_initial180_current_record.json"
        orders_path = CURRENT_RUN / "solve/dtn_port_diffraction_orders_3d.json"
        record = _json(record_path)
        if record.get("gates", {}).get("pass") is not True:
            raise ValueError("frozen parent current did not pass its numerical gates")
        if _sha256_file(CURRENT_RUN / "recovered_solution_storage.npz") != record[
            "recovered_solution_storage"
        ]["sha256"]:
            raise ValueError("frozen parent field storage differs from its record")
        if _sha256_file(orders_path) != record["power"]["channel_rows_sha256"]:
            raise ValueError("frozen parent modal rows differ from their record")
        mode_payload = _json(orders_path)
        power = base._scalar_power_record(label, record, mode_payload)
        return {"label": label, "record": record, "mode_payload": mode_payload, "power": power}

    if label not in {"Y6_1", "Y6_2"}:
        raise ValueError("candidate comparison permits only Y6_1/Y6_2 modal records")
    case_root = REFERENCE_ROOT / label
    record = _json(case_root / "restore_identity_record.json")
    if record.get("status") != "RESTORATION_IDENTITY_PASS_NOT_TASK43_QUALIFIED":
        raise ValueError(f"{label} reference restoration identity is not valid")
    orders_path = case_root / "numerical_output/dtn_port_diffraction_orders_3d.json"
    expected_sha = record["input_artifacts"][
        "numerical_output/dtn_port_diffraction_orders_3d.json"
    ]["sha256"]
    if _sha256_file(orders_path) != expected_sha:
        raise ValueError("selection reference mode rows differ from their identity record")
    mode_payload = _json(orders_path)
    power = base._scalar_power_record(label, record, mode_payload)
    return {"label": label, "record": record, "mode_payload": mode_payload, "power": power}


def _restore_case_fields(label: str, output_root: Path) -> dict[str, Any]:
    loaded = base._load_field_case(label, output_root)
    label, cfg, mesh_data, coefficients, expected_arrays, record, mode_payload = loaded
    mesh = mesh_data.mesh
    if mesh.comm.size != 1:
        raise RuntimeError(f"{label} reconstructed mesh is not serial")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    for name in base._IDENTITY_ARRAYS:
        if not np.array_equal(actual_arrays[name], expected_arrays[name]):
            raise ValueError(f"{label} reconstructed {name} differs from stored identity")
    field = fem.Function(space, name=f"{label}_full_recovered_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError(f"{label} coefficient vector differs from reconstructed space")
    field.x.array[:] = coefficients
    field.x.scatter_forward()
    return {
        "label": label,
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": base._axes_from_mesh(mesh),
        "record": record,
        "mode_payload": mode_payload,
        "power": base._scalar_power_record(label, record, mode_payload),
        "mesh_identity": {name: base._array_identity(values) for name, values in actual_arrays.items()},
    }


def _restore_candidate(candidate_run_root: Path, output_root: Path) -> dict[str, Any]:
    record_path = candidate_run_root / "task43_round1_candidate_record.json"
    record = _json(record_path)
    if record.get("schema") != "task43.round1_candidate_solve.v1":
        raise ValueError("candidate record has an unexpected schema")
    if record.get("gates", {}).get("pass") is not True:
        raise ValueError("candidate solver did not pass all hard numerical gates")
    if record.get("solver", {}).get("official_result") is not True:
        raise ValueError("candidate lacks a Task43 gated official-result identity")

    identity = record["candidate_identity"]
    candidate_id = str(identity["candidate_id"])
    plan_path = candidate_run_root / "candidate_plan.json"
    plan_sha = _sha256_file(plan_path)
    if plan_sha != identity["plan_sha256"]:
        raise ValueError("run-local candidate plan differs from its recorded identity")
    plan = _json(plan_path)
    if plan.get("task43_candidate", {}).get("candidate_id") != candidate_id:
        raise ValueError("candidate plan identity differs from the run record")
    if _sha256_file(ACCEPTANCE) != identity["acceptance_contract_sha256"]:
        raise ValueError("frozen round-one acceptance contract changed")

    # Round-one candidates are bound to the frozen initial perturbation. Later
    # candidates are checked against an already accepted parent by the caller.
    if not identity.get("accepted_parent_selection_sha256"):
        _validate_round1_candidate_inputs(
            candidate_plan_path=plan_path,
            candidate_id=candidate_id,
            parent_run_root=CURRENT_RUN,
            tightening_run_root=ROOT / "benchmarks/artifacts/task43/current_180/tightening_attempt2/run",
            marking_record_path=ROOT / "benchmarks/artifacts/task43/current_180/tightening_marking_q8/attempt2/tightening_marking_q8.json",
            acceptance_contract_path=ACCEPTANCE,
        )

    storage_path = candidate_run_root / "candidate_recovered_solution_storage.npz"
    storage_identity = record["recovered_solution_storage"]
    if _sha256_file(storage_path) != storage_identity["sha256"]:
        raise ValueError("candidate recovered coefficient storage differs from its record")
    orders_path = candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json"
    if _sha256_file(orders_path) != record["power"]["channel_rows_sha256"]:
        raise ValueError("candidate R13 modal rows differ from their record")
    mode_payload = _json(orders_path)

    cfg = _h100_config(
        kind="empty_h_active_p3",
        case_name=str(record["resolved_config"]["case_name"]),
        geometry_profile="initial_180",
    )
    cfg.stage4_local_h_refinement_plan = str(plan_path)
    mesh_data = build_stage4_local_h_mesh_data(cfg, plan_path, comm=MPI.COMM_WORLD)
    mesh = mesh_data.mesh
    axes = base._axes_from_mesh(mesh)
    actual_mesh = _assert_mesh_profile(
        mesh_data,
        axes,
        "candidate_initial180",
        candidate_plan=plan,
        candidate_plan_sha256=plan_sha,
    )
    if actual_mesh != record["numerical_controls"]["mesh"]:
        raise ValueError("rebuilt candidate mesh audit differs from the solve record")
    space = _create_nedelec_space(mesh, cfg)
    actual_arrays = base._actual_mesh_identity(mesh, space)
    expected_key_by_identity = {
        "mesh_geometry_coordinates_nm": "mesh_geometry_coordinates_nm",
        "mesh_geometry_dofmap": "mesh_geometry_dofmap",
        "mesh_owned_cell_global_ids": "mesh_owned_cell_global_ids",
        "mesh_cell_vertex_dofmap": "mesh_cell_vertex_dofmap",
        "p6_function_space_cell_dofmap": "p6_function_space_dofmap",
        "p6_owned_global_dof_block_ids": "p6_owned_global_dof_block_ids",
        "p6_ghost_global_dof_block_ids": "p6_ghost_global_dof_block_ids",
    }
    with np.load(storage_path, allow_pickle=False) as storage:
        for identity_key, storage_key in expected_key_by_identity.items():
            if not np.array_equal(actual_arrays[identity_key], storage[storage_key]):
                raise ValueError(f"candidate reconstructed {identity_key} differs from storage")
        coefficients = np.asarray(
            storage["recovered_p6_local_coefficients"], dtype=np.complex128
        ).copy()
    field = fem.Function(space, name=f"{candidate_id}_recovered_E")
    if field.x.array.shape != coefficients.shape:
        raise ValueError("candidate full-carrier coefficients differ from reconstructed space")
    field.x.array[:] = coefficients
    field.x.scatter_forward()
    aggregate = record["power"]["aggregate"]
    power = {
        **{key: float(aggregate[key]) for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")},
        "A_volume": float(record["power"]["A_volume_total"]),
    }
    return {
        "label": candidate_id,
        "candidate_id": candidate_id,
        "candidate_action": plan["task43_candidate"]["action"],
        "cfg": cfg,
        "mesh_data": mesh_data,
        "field": field,
        "axes": axes,
        "record": record,
        "mode_payload": mode_payload,
        "power": power,
        "mesh_identity": {name: base._array_identity(values) for name, values in actual_arrays.items()},
        "storage_sha256": storage_identity["sha256"],
        "plan_sha256": plan_sha,
    }


def _load_accepted_parent(selection_path: Path) -> dict[str, Any]:
    """Resolve an accepted parent using the shared JSON/hash identity reader."""

    return load_accepted_parent_artifacts(
        selection_path,
        artifact_root=ROOT,
        acceptance_contract_path=ACCEPTANCE,
    )


def _validate_candidate_physics(
    candidate: dict[str, Any],
    parent: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    controls = candidate["record"]["numerical_controls"]
    expected_q = calibration["recorded_quadrature_and_cutoff_identity"]["expected"]
    actual_q = {
        "volume_degree": int(controls["volume_quadrature_degree"]),
        "surface_and_incident_degree": int(
            controls["incident_and_port_quadrature_degree"]
        ),
        "volume_rule": str(controls["volume_quadrature_rule"]),
        "cutoff_policy": str(controls["sparse_cutoff_policy"]),
        "cutoff_relative_tolerance": float(
            controls["sparse_cutoff_relative_tolerance"]
        ),
    }
    if actual_q != expected_q:
        raise ValueError("candidate quadrature/cutoff differs from the frozen Task43 profile")
    expected_scale = "boundary_magnitude_scaled_r5_v1"
    actual_scale = str(controls["port_amplitude_scale_policy"])
    if actual_scale != expected_scale:
        raise ValueError("candidate port amplitudes use an unexpected boundary scale")

    expected_physics = calibration["physical_configuration_identity"]["shared_identity"]
    actual_physics = base._physical_configuration_identity(candidate["cfg"])
    if actual_physics != expected_physics:
        raise ValueError("candidate resolved physical configuration differs from frozen references")
    recorded_config = candidate["record"].get("resolved_config")
    rebuilt_config = candidate["cfg"].as_jsonable()
    config_identity_keys = (
        "geometry_kind",
        "scattering_background",
        "polarization_kind",
        "electric_field_unit",
        "magnetic_field_unit",
        "lambda0",
        "period_x",
        "period_y",
        "physical_z_min",
        "physical_z_max",
        "domain_z_min",
        "domain_z_max",
        "grating_bounds",
        "interface_z",
        "air_height",
        "substrate_thickness",
        "incident_theta_deg",
        "incident_phi_deg",
        "incident_amplitude",
        "incident_e0_v_per_m",
        "n_air",
        "mu_r",
        "n_substrate",
        "n_grating",
        "eps_air",
        "eps_substrate",
        "eps_grating",
        "k0",
        "wavevector",
        "polarization",
        "magnetic_field_scale_A_per_m",
    )
    if not isinstance(recorded_config, dict) or any(
        recorded_config.get(key) != rebuilt_config.get(key)
        for key in config_identity_keys
    ):
        raise ValueError("candidate run-record config differs from its reconstructed solve config")
    cfg = candidate["cfg"]
    volume = float(cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min))
    if (
        abs(complex(cfg.n_air) - 1.0) > 1.0e-14
        or abs(complex(cfg.mu_r) - 1.0) > 1.0e-14
        or abs(complex(cfg.incident_amplitude) - 1.0) > 1.0e-14
        or abs(float(cfg.incident_e0_v_per_m) - 1.0) > 1.0e-14
        or abs(volume - 350000.0) > 1.0e-8
    ):
        raise ValueError("candidate does not satisfy the fixed unit-incident field floors")

    parent_rows = parent["mode_payload"]["orders"]
    candidate_rows = candidate["mode_payload"]["orders"]
    if len(parent_rows) != 612 or len(candidate_rows) != 612:
        raise ValueError("parent or candidate modal output does not contain 612 rows")
    physical_fields = ("alpha", "gamma", "beta", "kz", "refractive_index")
    flags = ("direction", "medium", "vertical_sign", "propagating", "power_carrying")
    max_differences: dict[str, float] = {}
    for index, (parent_row, candidate_row) in enumerate(
        zip(parent_rows, candidate_rows, strict=True)
    ):
        if base._mode_key(parent_row) != base._mode_key(candidate_row):
            raise ValueError(f"candidate ordered modal key differs at row {index}")
        for name in flags:
            if parent_row[name] != candidate_row[name]:
                raise ValueError(f"candidate modal {name} differs at row {index}")
        for name in physical_fields:
            difference = float(
                np.max(
                    np.abs(
                        np.asarray(parent_row[name], dtype=np.float64)
                        - np.asarray(candidate_row[name], dtype=np.float64)
                    )
                )
            )
            max_differences[name] = max(max_differences.get(name, 0.0), difference)
            if not np.allclose(
                parent_row[name], candidate_row[name], rtol=1.0e-12, atol=1.0e-14
            ):
                raise ValueError(f"candidate modal {name} differs at row {index}")
    return {
        "resolved_physics_matches_frozen_reference_identity": True,
        "recorded_resolved_config_matches_rebuilt_config": True,
        "resolved_q_and_cutoff": actual_q,
        "boundary_amplitude_scale_policy": actual_scale,
        "unit_incident_and_volume_floor_validated": True,
        "ordered_modal_physics_fields_checked": [*physical_fields, *flags],
        "maximum_absolute_modal_parameter_differences": max_differences,
    }


def _recompute_candidate_hard_gates(
    record: dict[str, Any], mode_payload: dict[str, Any], contract: dict[str, Any],
    *, allow_legacy_initial_parent: bool = False,
) -> dict[str, Any]:
    solver = record["solver"]
    action = solver["independent_active_action"]
    a6_residual = float(action["full_solver_gauge_residual"]["raw_l2_norm"])
    independent_rhs = float(action["rhs"]["raw_l2_norm"])
    condensed = solver["condensed_residual"]
    condensed_residual = float(condensed["linear_system_residual_norm"])
    condensed_rhs = float(condensed["linear_system_rhs_norm"])
    raw_norms_valid = all(
        np.isfinite(value) and value >= 0.0
        for value in (a6_residual, independent_rhs, condensed_residual, condensed_rhs)
    )
    residual_denominators_positive = independent_rhs > 0.0 and condensed_rhs > 0.0
    a6_relative = (
        a6_residual / independent_rhs
        if raw_norms_valid and residual_denominators_positive
        else float("nan")
    )
    condensed_relative = (
        condensed_residual / condensed_rhs
        if raw_norms_valid and residual_denominators_positive
        else float("nan")
    )
    power = record["power"]
    aggregate = power["aggregate"]
    a_volume = float(power["A_volume_total"])
    r_total = float(aggregate["R_total"])
    t_total = float(aggregate["T_total"])
    energy_closure = abs(1.0 - r_total - t_total - a_volume)

    rows = mode_payload.get("orders")
    if not isinstance(rows, list) or len(rows) != 612:
        raise ValueError("candidate output inventory is not exactly 612 ordered modes")
    keys = [base._mode_key(row) for row in rows]
    if len(set(keys)) != 612:
        raise ValueError("candidate output inventory contains duplicate modal identities")
    finite_inventory = True
    for row in rows:
        numeric_values = [row.get(key) for key in ("power_ratio", "R", "T")]
        numeric_values.extend(
            row.get(key, ())
            for key in ("outgoing_amplitude_at_boundary", "alpha", "gamma", "beta", "kz", "refractive_index")
        )
        try:
            finite_inventory = finite_inventory and all(
                np.isfinite(np.asarray(value, dtype=np.float64)).all()
                for value in numeric_values
            )
        except (TypeError, ValueError):
            finite_inventory = False

    storage = record["recovered_solution_storage"]
    trace_rows = int(storage["active_trace_rows"])
    interior_rows = int(storage["active_cell_interior_rows"])
    independent_dofs = trace_rows + interior_rows
    storage_declared_dofs = storage.get("independent_active_fe_dofs")
    active_space = record.get("numerical_controls", {}).get("active_space") or {}
    summary_declared_dofs = active_space.get("independent_active_fe_dofs")
    dof_declarations_match = (
        storage_declared_dofs is not None
        and summary_declared_dofs is not None
        and int(storage_declared_dofs) == independent_dofs
        and int(summary_declared_dofs) == independent_dofs
    )
    residual_groups = action["groups"]
    dof_row_counts_match = (
        trace_rows == int(residual_groups["independent_active_trace_residual"]["row_count"])
        and interior_rows
        == int(residual_groups["independent_active_interior_residual"]["row_count"])
    )
    # The frozen initial record predates the two duplicate FE declarations.
    # Only its explicit parent role may use the original raw row identities.
    legacy_initial_identity = (
        allow_legacy_initial_parent
        and record.get("schema") == "task43.initial_180_cell_active_p3_current.v1"
        and record.get("case_id") == "current_active_p3_initial180_mpi1"
        and "independent_active_fe_dofs" not in storage
        and "active_space" not in record.get("numerical_controls", {})
        and trace_rows == 8640 and interior_rows == 6480
        and independent_dofs == 15120
        and action.get("rows") == {
            "independent_trace": 8640, "active_cell_interior": 6480,
            "modal_lower": 612,
        }
        and dof_row_counts_match
    )
    hard_limits = contract["final_tolerances"]
    mesh_audit_pass = (
        record["numerical_controls"].get("local_h_actual_audit", {}).get("pass") is True
    )
    raw_checks = {
        "residual_norms_are_finite_and_nonnegative": raw_norms_valid,
        "residual_denominators_are_positive": residual_denominators_positive,
        "independent_A6_le_1e-6": bool(
            np.isfinite(a6_relative)
            and a6_relative <= float(hard_limits["independent_full_active_relative_residual"])
        ),
        "condensed_residual_le_1e-9": bool(
            np.isfinite(condensed_relative)
            and condensed_relative <= float(hard_limits["condensed_direct_relative_residual"])
        ),
        "energy_closure_le_1e-5": bool(
            np.isfinite(energy_closure)
            and energy_closure
            <= float(hard_limits["absolute_energy_closure_1_minus_R_minus_T_minus_A_volume"])
        ),
        "finite_unique_612_mode_inventory": bool(finite_inventory and len(set(keys)) == 612),
        "independent_dofs_match_residual_rows": bool(
            independent_dofs > 0 and dof_row_counts_match
        ),
        ("legacy_initial_parent_raw_FE_identity_matches"
         if legacy_initial_identity
         else "independent_dofs_match_both_record_declarations"): (
            legacy_initial_identity or dof_declarations_match
        ),
        "actual_mesh_and_closure_audit_pass": mesh_audit_pass,
        "recorded_gate_and_official_identity_pass": bool(
            record.get("gates", {}).get("pass") is True
            and record.get("solver", {}).get("official_result") is True
        ),
    }
    return {
        "classification": "checker_recomputed_from_raw_record_fields",
        "independent_A6": {
            "residual_raw_l2_norm": a6_residual,
            "independent_rhs_raw_l2_norm": independent_rhs,
            "relative": a6_relative,
        },
        "condensed_residual": {
            "residual_raw_l2_norm": condensed_residual,
            "rhs_raw_l2_norm": condensed_rhs,
            "relative": condensed_relative,
        },
        "energy_closure": {
            "R_total": r_total,
            "T_total": t_total,
            "A_volume": a_volume,
            "absolute_1_minus_R_minus_T_minus_A": energy_closure,
        },
        "channel_inventory": {
            "row_count": len(rows),
            "unique_key_count": len(set(keys)),
            "all_numeric_outputs_finite": bool(finite_inventory),
        },
        "actual_space": {
            "independent_trace_rows": trace_rows,
            "active_cell_interior_rows": interior_rows,
            "independent_FE_dofs": independent_dofs,
            "storage_declared_independent_FE_dofs": storage_declared_dofs,
            "active_space_declared_independent_FE_dofs": summary_declared_dofs,
            "both_declarations_match_recomputed_sum": dof_declarations_match,
            "declaration_validation_route": (
                "explicit_legacy_initial_parent_storage_and_A6_rows"
                if legacy_initial_identity else "both_record_declarations_required"
            ),
            "residual_row_counts_match": dof_row_counts_match,
        },
        "hard_checks": raw_checks,
        "pass": all(raw_checks.values()),
    }


def _axes_subset(
    candidate_axes: tuple[np.ndarray, ...], common_axes: tuple[np.ndarray, ...]
) -> bool:
    for candidate, common in zip(candidate_axes, common_axes, strict=True):
        for value in candidate:
            index = int(np.searchsorted(common, value))
            neighbors = [slot for slot in (index - 1, index) if 0 <= slot < common.size]
            if not neighbors or min(abs(float(common[slot]) - float(value)) for slot in neighbors) > 1.0e-12:
                return False
    return True


def _sample_field(case: dict[str, Any], points: np.ndarray) -> dict[str, np.ndarray]:
    export = prepare_cell_local_vector_field_export(case["field"])
    values = sample_cell_local_vector_fields(
        {"E": export.electric_dgq6, "curl_E": export.curl_electric_dgq6},
        points,
        batch_size=32768,
    )
    if values is None:
        raise RuntimeError("MPI1 field sampler returned no samples")
    return values


def _j_infinity(
    modal: dict[str, Any], field_metrics: dict[str, Any]
) -> dict[str, Any]:
    scaled: dict[str, float] = {}
    tolerances = {
        "R_total": 1.0e-5,
        "T_total": 1.0e-5,
        "A_volume": 1.0e-5,
        "R00_s": 1.0e-6,
        "R00_p": 1.0e-6,
        "R00_total": 1.0e-5,
    }
    for key, tolerance in tolerances.items():
        scaled[f"power.{key}"] = abs(float(modal["power_absolute_differences"][key])) / tolerance
    scaled["power.max_individual_channel"] = (
        float(modal["maximum_individual_channel_power_ratio_absolute_difference"]) / 1.0e-6
    )
    for group, values in modal["boundary_amplitude_groups"].items():
        scaled[f"amplitude.{group}"] = float(values["relative_with_unit_incident_modal_floor"]) / 1.0e-4
    for name in (
        "E_total_code",
        "H_total_A_per_m",
        "E_scattered_code",
        "H_scattered_A_per_m",
    ):
        scaled[f"field.{name}"] = float(
            field_metrics[name]["relative_to_reference_or_floor"]
        ) / 1.0e-4
    scaled["field.G"] = float(
        field_metrics["G"]["relative_with_incident_floor"]
    ) / 1.0e-4
    if not scaled or not all(np.isfinite(value) for value in scaled.values()):
        raise ValueError("J_infinity contains non-finite observable components")
    witness = max(scaled, key=scaled.__getitem__)
    return {"value": scaled[witness], "witness": witness, "components": scaled}


def compare_candidate(
    candidate_run_root: Path,
    output_root: Path,
    parent_selection_path: Path | None = None,
) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("round-one candidate comparison currently requires MPI1")
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite comparison attempt {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    source_start = base._source_snapshot()
    source_start["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    source_start["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    (output_root / "source_identity_start.json").write_text(
        json.dumps(source_start, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    contract = _json(ACCEPTANCE)
    comparison_contract_path = ROOT / contract["evidence"]["comparison_contract"]["path"]
    calibration_path = ROOT / contract["evidence"]["reference_and_quadrature"]["path"]
    if _sha256_file(comparison_contract_path) != contract["evidence"][
        "comparison_contract"
    ]["sha256"]:
        raise ValueError("frozen comparison contract differs from round-one acceptance")
    if _sha256_file(calibration_path) != contract["evidence"][
        "reference_and_quadrature"
    ]["sha256"]:
        raise ValueError("reference calibration differs from round-one acceptance")
    comparison_contract = _json(comparison_contract_path)
    calibration_record = _json(calibration_path)
    if (
        calibration_record.get("status")
        != "REFERENCE_PAIR_FIELD_AND_MODAL_COMPARISON_COMPLETE_CANDIDATE_RUNS_PENDING"
        or calibration_record.get("reference_roles")
        != {"selection": "Y6_1", "calibration": "Y6_2", "holdout": "Y5_1_not_read"}
        or calibration_record.get("source_identity", {}).get(
            "unchanged_during_comparison"
        )
        is not True
    ):
        raise ValueError("frozen reference calibration is not a complete, source-stable pair")
    accepted_parent = (
        None if parent_selection_path is None else _load_accepted_parent(parent_selection_path)
    )
    if accepted_parent is None:
        parent_modal = _load_modal_case("current_180")
    else:
        parent_record = accepted_parent["record"]
        parent_orders_path = accepted_parent["run_root"] / "solve/dtn_port_diffraction_orders_3d.json"
        if _sha256_file(parent_orders_path) != parent_record["power"]["channel_rows_sha256"]:
            raise ValueError("accepted parent modal rows differ from their record")
        parent_modal = {"record": parent_record, "mode_payload": _json(parent_orders_path)}
    parent_gate_recalculation = _recompute_candidate_hard_gates(
        parent_modal["record"], parent_modal["mode_payload"], comparison_contract,
        allow_legacy_initial_parent=accepted_parent is None,
    )
    (output_root / "parent_raw_hard_gate_precheck.json").write_text(
        json.dumps(parent_gate_recalculation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not parent_gate_recalculation["pass"]:
        raise ValueError("comparison parent fails raw hard-gate recalculation")
    candidate = _restore_candidate(candidate_run_root, output_root)
    has_accepted_parent_binding = bool(
        candidate["record"].get("candidate_identity", {}).get(
            "accepted_parent_selection_sha256"
        )
    )
    if has_accepted_parent_binding != (parent_selection_path is not None):
        raise ValueError(
            "candidate parent-selection binding and comparator parent argument disagree"
        )
    if accepted_parent is not None:
        candidate_plan = _json(candidate_run_root / "candidate_plan.json")
        provenance = candidate_plan.get("task43_candidate", {}).get("provenance", {})
        parent_hashes = accepted_parent["hashes"]
        expected_parent_identity = {
            "accepted_parent_selection_sha256": accepted_parent["selection_sha256"],
            "parent_run_root": str(accepted_parent["run_root"]),
            "parent_candidate_id": accepted_parent["selected"]["candidate_id"],
            "parent_case_record_sha256": parent_hashes["record_sha256"],
            "parent_recovered_storage_sha256": parent_hashes["storage_sha256"],
            "parent_plan_sha256": parent_hashes["plan_sha256"],
            "parent_comparison_sha256": parent_hashes["comparison_record_sha256"],
            "acceptance_contract_sha256": _sha256_file(ACCEPTANCE),
        }
        if any(provenance.get(key) != value for key, value in expected_parent_identity.items()):
            raise ValueError("candidate plan is not bound to the accepted parent artifacts")
        if Path(str(provenance.get("accepted_parent_selection_record_path"))).resolve() != accepted_parent["selection_path"]:
            raise ValueError("candidate plan names a different accepted selection record")
        candidate_identity = candidate["record"].get("candidate_identity", {})
        if (
        candidate_identity.get("accepted_parent_selection_sha256")
            != accepted_parent["selection_sha256"]
            or candidate_identity.get("parent_candidate_id")
            != accepted_parent["selected"]["candidate_id"]
        ):
            raise ValueError("candidate solve record is not bound to the accepted parent selection")
    if accepted_parent is None:
        parent_candidate = None
        parent_label = "current_180"
    else:
        parent_candidate = _restore_candidate(
            accepted_parent["run_root"], output_root / "accepted_parent_restore"
        )
        if parent_candidate["candidate_id"] != accepted_parent["selected"]["candidate_id"]:
            raise ValueError("restored parent candidate differs from accepted selection")
        parent_modal = {
            "label": parent_candidate["candidate_id"],
            "record": parent_candidate["record"],
            "mode_payload": parent_candidate["mode_payload"],
            "power": parent_candidate["power"],
        }
        parent_label = parent_candidate["candidate_id"]
    selection_modal = _load_modal_case("Y6_1")
    calibration_modal = _load_modal_case("Y6_2")
    calibration_mode_validation = base._validate_mode_physics(
        {
            "current_180": {**parent_modal, "label": "current_180"},
            "Y6_1": selection_modal,
            "Y6_2": calibration_modal,
        }
    )
    calibration_q_validation = base._validate_recorded_quadrature_and_cutoff(
        {
            "current_180": {**parent_modal, "label": "current_180"},
            "Y6_1": selection_modal,
            "Y6_2": calibration_modal,
        }
    )
    candidate_physics_validation = _validate_candidate_physics(
        candidate, parent_modal, calibration_record
    )
    candidate_gate_recalculation = _recompute_candidate_hard_gates(
        candidate["record"], candidate["mode_payload"], comparison_contract
    )
    q8_identity = calibration_record["quadrature"]["q8"]
    cached_samples_path = Path(q8_identity["sample_bundle"])
    if not cached_samples_path.is_absolute():
        cached_samples_path = ROOT / cached_samples_path
    if _sha256_file(cached_samples_path) != q8_identity["sample_bundle_sha256"]:
        raise ValueError("frozen q8 reference sample bundle differs from its record")
    with np.load(cached_samples_path, allow_pickle=False) as archive:
        cached = {key: np.asarray(archive[key]).copy() for key in archive.files}
    cached_axes = tuple(
        np.asarray(axis, dtype=np.float64)
        for axis in q8_identity["axis_breakpoints_nm"]
    )
    cached_rule = build_common_volume_quadrature([cached_axes], gauss_order=8)
    if cached_rule.rule_sha256 != q8_identity["rule_sha256"]:
        raise ValueError("cached q8 points do not match the frozen quadrature identity")
    if not np.array_equal(cached_rule.points_nm, cached["points_nm"]) or not np.array_equal(
        cached_rule.weights_nm3, cached["weights_nm3"]
    ):
        raise ValueError("cached q8 sample coordinates/weights differ from regenerated rule")

    reuse_cached = _axes_subset(candidate["axes"], cached_axes) and (
        parent_candidate is None or _axes_subset(parent_candidate["axes"], cached_axes)
    )
    cases: dict[str, dict[str, Any]] = {}
    if reuse_cached:
        quadrature = cached_rule
        parent_samples = (
            {"E": cached["current_180_E_code"], "curl_E": cached["current_180_curl_E_code"]}
            if parent_candidate is None
            else _sample_field(parent_candidate, quadrature.points_nm)
        )
        sampled = {
            parent_label: parent_samples,
            "Y6_1": {"E": cached["Y6_1_E_code"], "curl_E": cached["Y6_1_curl_E_code"]},
        }
    else:
        cases = {"Y6_1": _restore_case_fields("Y6_1", output_root)}
        if parent_candidate is None:
            cases["current_180"] = _restore_case_fields("current_180", output_root)
            parent_case = cases["current_180"]
        else:
            parent_case = parent_candidate
        # The frozen q8 axes include both reference meshes; add actual parent
        # and candidate leaf boundaries, then resample only Y6_1 and the parent.
        axes_to_merge = [cached_axes]
        axes_to_merge.extend((parent_case["axes"], cases["Y6_1"]["axes"]))
        axes_to_merge.append(candidate["axes"])
        quadrature = build_common_volume_quadrature(axes_to_merge, gauss_order=8)
        sampled = {"Y6_1": _sample_field(cases["Y6_1"], quadrature.points_nm)}
        sampled[parent_label] = _sample_field(parent_case, quadrature.points_nm)

    candidate_samples = _sample_field(candidate, quadrature.points_nm)
    sampled[candidate["label"]] = candidate_samples
    if parent_candidate is not None:
        cfg = parent_candidate["cfg"]
    elif "current_180" not in cases:
        current_record = parent_modal["record"]
        cfg = _h100_config(
            kind="empty_h_active_p3",
            case_name=str(current_record["resolved_config"]["case_name"]),
            geometry_profile="initial_180",
        )
    else:
        cfg = cases["current_180"]["cfg"]
    parent_modal_case = {**parent_modal, "label": parent_label}
    reference_modal_case = {**selection_modal, "label": "Y6_1"}
    candidate_modal_case = {**candidate, "label": candidate["candidate_id"]}
    parent_modal_metrics = base._modal_comparison(reference_modal_case, parent_modal_case)
    candidate_modal_metrics = base._modal_comparison(reference_modal_case, candidate_modal_case)
    parent_field_metrics = base._field_metrics(
        sampled["Y6_1"], sampled[parent_label], quadrature.points_nm,
        quadrature.weights_nm3, cfg,
    )
    candidate_field_metrics = base._field_metrics(
        sampled["Y6_1"], candidate_samples, quadrature.points_nm,
        quadrature.weights_nm3, cfg,
    )
    parent_j = _j_infinity(parent_modal_metrics, parent_field_metrics)
    candidate_j = _j_infinity(candidate_modal_metrics, candidate_field_metrics)

    candidate_global_ids, candidate_point_slots = base._cell_slot_for_points(
        candidate["mesh_data"].mesh,
        candidate["axes"],
        quadrature.points_nm,
    )
    contributions = accumulate_physical_g_cell_contributions(
        sampled["Y6_1"]["E"], candidate_samples["E"],
        sampled["Y6_1"]["curl_E"], candidate_samples["curl_E"],
        quadrature.weights_nm3, candidate_point_slots,
        cell_global_ids=candidate_global_ids,
        k0_per_nm=float(cfg.k0),
    )
    marked_ids, marking = dorfler_mark_physical_g(
        candidate_global_ids, contributions, theta=0.5
    )
    contribution_sum = float(np.sum(contributions, dtype=np.float64))
    expected_difference_squared = float(
        candidate_field_metrics["G"]["difference_g_norm"]
    ) ** 2
    contribution_closure = abs(contribution_sum - expected_difference_squared) / max(
        expected_difference_squared, 1.0e-300
    )
    if contribution_closure > 2.0e-12:
        raise ValueError("candidate leaf G contributions do not close to the full-volume metric")

    eta_parent = float(parent_field_metrics["G"]["relative_with_incident_floor"])
    eta_candidate = float(candidate_field_metrics["G"]["relative_with_incident_floor"])
    epsilon_g = float(contract["acceptance"]["epsilon_G"])
    epsilon_j = float(contract["acceptance"]["epsilon_J"])
    parent_dofs = int(parent_gate_recalculation["actual_space"]["independent_FE_dofs"])
    candidate_dofs = int(
        candidate_gate_recalculation["actual_space"]["independent_FE_dofs"]
    )
    dof_increment = candidate_dofs - parent_dofs
    g_improvement = eta_parent - eta_candidate
    gates = {
        "candidate_solver_hard_gates_pass": candidate_gate_recalculation["pass"],
        "positive_actual_independent_dof_increment": dof_increment > 0,
        "G_decrease_exceeds_frozen_noise": g_improvement > epsilon_g,
        "J_infinity_within_frozen_noise": candidate_j["value"] <= parent_j["value"] + epsilon_j,
    }
    gates["pass"] = all(gates.values())

    sample_path = output_root / (
        "round1_candidate_shared_volume_q8.npz"
        if accepted_parent is None
        else "candidate_shared_volume_q8.npz"
    )
    sample_arrays = {
        "points_nm": quadrature.points_nm,
        "weights_nm3": quadrature.weights_nm3,
        "candidate_cell_global_ids": candidate_global_ids,
        "point_candidate_cell_local_slots": candidate_point_slots,
    }
    for label, values in sampled.items():
        sample_arrays[f"{label}_E_code"] = values["E"]
        sample_arrays[f"{label}_curl_E_code"] = values["curl_E"]
    np.savez_compressed(sample_path, **sample_arrays)

    source_end = base._source_snapshot()
    source_end["candidate_comparator_sha256"] = _sha256_file(Path(__file__))
    source_end["candidate_records_sha256"] = _sha256_file(CANDIDATE_RECORDS)
    sources_unchanged = bool(
        source_start["git_head"] == source_end["git_head"]
        and source_start["file_sha256"] == source_end["file_sha256"]
        and source_start["candidate_comparator_sha256"]
        == source_end["candidate_comparator_sha256"]
        and source_start["candidate_records_sha256"]
        == source_end["candidate_records_sha256"]
    )
    if not sources_unchanged:
        raise RuntimeError("comparison source identity changed during candidate postprocessing")
    record = {
        "schema": "task43.round1-candidate-comparison.v1",
        "classification": "measured_candidate_against_frozen_selection_reference_and_acceptance_contract",
        "candidate_id": candidate["candidate_id"],
        "candidate_action": candidate["candidate_action"],
        "candidate_run_root": str(candidate_run_root.resolve()),
        "candidate_record_sha256": _sha256_file(candidate_run_root / "task43_round1_candidate_record.json"),
        "candidate_storage_sha256": candidate["storage_sha256"],
        "candidate_plan_sha256": candidate["plan_sha256"],
        "selection_reference": "Y6_1",
        "calibration_reference": "Y6_2",
        "holdout_read": False,
        "final_p6_control_read": False,
        "verified_source_contracts": {
            "round1_acceptance_contract_sha256": _sha256_file(ACCEPTANCE),
            "comparison_contract_sha256": _sha256_file(comparison_contract_path),
            "reference_calibration_sha256": _sha256_file(calibration_path),
            "reference_mode_physics_validation": calibration_mode_validation,
            "reference_q_and_cutoff_validation": calibration_q_validation,
            "candidate_physics_validation": candidate_physics_validation,
            "candidate_raw_hard_gate_recalculation": candidate_gate_recalculation,
            "parent_raw_hard_gate_recalculation": parent_gate_recalculation,
        },
        "parent_identity": (
            None
            if accepted_parent is None
            else {
                "selection_record_path": str(accepted_parent["selection_path"]),
                "selection_record_sha256": accepted_parent["selection_sha256"],
                "candidate_id": accepted_parent["selected"]["candidate_id"],
                "run_root": str(accepted_parent["run_root"]),
                **accepted_parent["hashes"],
            }
        ),
        "q8": {
            "rule_sha256": quadrature.rule_sha256,
            "axis_breakpoints_nm": [axis.tolist() for axis in quadrature.axis_breakpoints_nm],
            "sample_count": quadrature.point_count,
            "reused_frozen_reference_rule_and_selection_samples": reuse_cached,
            "sample_bundle": str(sample_path),
            "sample_bundle_sha256": _sha256_file(sample_path),
            "integrated_domain_volume_nm3": float(np.sum(quadrature.weights_nm3)),
        },
        "field_metrics_vs_selection_reference": {
            "parent": parent_field_metrics,
            "candidate": candidate_field_metrics,
        },
        "modal_and_power_metrics_vs_selection_reference": {
            "parent": parent_modal_metrics,
            "candidate": candidate_modal_metrics,
        },
        "J_infinity": {
            "parent": parent_j,
            "candidate": candidate_j,
            "epsilon_J": epsilon_j,
        },
        "selection": {
            "eta_parent": eta_parent,
            "eta_candidate": eta_candidate,
            "G_improvement": g_improvement,
            "epsilon_G": epsilon_g,
            "parent_independent_FE_dofs": parent_dofs,
            "candidate_independent_FE_dofs": candidate_dofs,
            "actual_added_independent_FE_dofs": dof_increment,
            "primary_score_G_improvement_per_added_independent_FE_dof": (
                g_improvement / dof_increment if dof_increment > 0 else None
            ),
            "primary_score_noise_half_width": (
                epsilon_g / dof_increment if dof_increment > 0 else None
            ),
            "primary_score_noise_interval": (
                {
                    "lower": (g_improvement - epsilon_g) / dof_increment,
                    "upper": (g_improvement + epsilon_g) / dof_increment,
                    "half_width": epsilon_g / dof_increment,
                    "formula": "(eta_parent - eta_candidate +/- epsilon_G) / actual_added_independent_FE_dofs",
                }
                if dof_increment > 0
                else None
            ),
            "gates": gates,
            "status": "eligible_under_frozen_acceptance_contract" if gates["pass"] else "rejected_under_frozen_acceptance_contract",
        },
        "candidate_leaf_G_contributions": {
            "cell_global_ids": candidate_global_ids.tolist(),
            "cell_g_error_squared": contributions.tolist(),
            "marked_global_cell_ids": marked_ids.tolist(),
            "marking": marking,
            "sum_vs_full_volume_g_difference_relative_closure": contribution_closure,
        },
        "source_identity_start": source_start,
        "source_identity_end": source_end,
        "sources_unchanged_during_comparison": sources_unchanged,
        "wall_seconds": time.perf_counter() - started,
    }
    output_name = (
        "round1_candidate_comparison_v1.json"
        if accepted_parent is None
        else "candidate_comparison_v2.json"
    )
    record["schema"] = (
        "task43.round1-candidate-comparison.v1"
        if accepted_parent is None
        else "task43.candidate-comparison.v2"
    )
    record["parent_candidate_id"] = None if accepted_parent is None else parent_label
    output_path = output_root / output_name
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "stage": "candidate_comparison_complete",
                "candidate_id": candidate["candidate_id"],
                "status": record["selection"]["status"],
                "eta_candidate": eta_candidate,
                "J_candidate": candidate_j["value"],
                "record": str(output_path),
                "wall_seconds": record["wall_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-run-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--accepted-parent-selection-record", type=Path)
    args = parser.parse_args()
    if not args.attempt_id or Path(args.attempt_id).name != args.attempt_id:
        parser.error("--attempt-id must be one path component")
    compare_candidate(
        args.candidate_run_root.resolve(),
        DEFAULT_OUTPUT / args.attempt_id,
        args.accepted_parent_selection_record,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
