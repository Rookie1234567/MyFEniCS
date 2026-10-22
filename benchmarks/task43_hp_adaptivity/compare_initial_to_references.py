"""Compare the frozen Task43 current with Y6_1/Y6_2 on shared volume rules.

This post-processing runner rebuilds each recorded mesh and function ordering,
then evaluates the stored full fields.  It performs no PDE solve and is limited
to the current, selection-reference, and calibration-reference roles; the
Y5_1 holdout is not an accepted input.
"""

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

from benchmarks.task43_hp_adaptivity.h100_anchor import _h100_config
from benchmarks.task43_hp_adaptivity.reference_restore import (
    _configure_historical_direct_route,
    _load_inventory_entry,
)
from src.adaptivity.physical_g_error import (
    accumulate_physical_g_cell_contributions,
    attribute_points_to_axis_aligned_cells,
    dorfler_mark_physical_g,
    physical_g_difference_metrics,
)
from src.adaptivity.stage4_local_h import build_stage4_local_h_mesh_data
from src.common.analytic_fields_3d import (
    electric_field_code_values,
    magnetic_field_code_values,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    magnetic_field_from_electric_curl,
    scattered_field_samples,
    weighted_vector_field_metrics,
)
from src.postprocessing.physical_field_sampling import (
    prepare_cell_local_vector_field_export,
    sample_cell_local_vector_fields,
)
from src.solvers.common_3d_solve import _create_nedelec_space

ROOT = Path(__file__).resolve().parents[2]
CURRENT_RUN = ROOT / "benchmarks/artifacts/task43/current_180/attempt1/run"
REFERENCE_ROOT = ROOT / "benchmarks/artifacts/task43/reference_imports/attempt2"
DEFAULT_OUTPUT_ROOT = ROOT / "benchmarks/artifacts/task43/reference_comparison"
_IDENTITY_ARRAYS = (
    "mesh_geometry_coordinates_nm",
    "mesh_geometry_dofmap",
    "mesh_owned_cell_global_ids",
    "mesh_cell_vertex_dofmap",
    "p6_function_space_cell_dofmap",
    "p6_owned_global_dof_block_ids",
    "p6_ghost_global_dof_block_ids",
)
SOURCE_FILES = (
    "benchmarks/task43_hp_adaptivity/compare_initial_to_references.py",
    "benchmarks/task43_hp_adaptivity/h100_anchor.py",
    "benchmarks/task43_hp_adaptivity/profile.py",
    "benchmarks/task43_hp_adaptivity/reference_restore.py",
    "src/adaptivity/dyadic_hexa_broken_mesh.py",
    "src/adaptivity/dyadic_hexa_refinement.py",
    "src/adaptivity/exact_sequence_variable_p.py",
    "src/adaptivity/hcurl_broken_cell_trace.py",
    "src/adaptivity/hcurl_broken_trace_graph.py",
    "src/adaptivity/physical_g_error.py",
    "src/adaptivity/stage4_local_h.py",
    "src/adaptivity/variable_p_degree_plan.py",
    "src/adaptivity/variable_p_entity_map.py",
    "src/common/analytic_fields_3d.py",
    "src/common/config_3d.py",
    "src/common/modes_3d.py",
    "src/constraints/floquet_3d.py",
    "src/geometry/mesh_builder_3d.py",
    "src/geometry/task43_hp_adaptivity_axis_plan.py",
    "src/io/input_validation.py",
    "src/postprocessing/diffraction_3d.py",
    "src/postprocessing/flat_layer_reference_3d.py",
    "src/postprocessing/physical_field_comparison.py",
    "src/postprocessing/physical_field_sampling.py",
    "src/postprocessing/postprocess_3d.py",
    "src/postprocessing/rta_3d.py",
    "src/solvers/common_3d_case_flow.py",
    "src/solvers/common_3d_fields.py",
    "src/solvers/common_3d_forms.py",
    "src/solvers/common_3d_postprocess.py",
    "src/solvers/common_3d_solve.py",
    "src/solvers/common_3d_utils.py",
    "src/solvers/dtn_port_3d.py",
    "src/solvers/hcurl_blocked_gram_tensor.py",
    "src/solvers/hcurl_variable_p_assembly.py",
    "src/solvers/hcurl_variable_p_local.py",
    "src/solvers/hcurl_variable_p_reduction.py",
    "src/solvers/independent_active_action.py",
    "src/solvers/solve_maxwell_3d_stage_4b_block_grating.py",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(array.view(np.uint8))
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest.hexdigest(),
    }


def _source_snapshot() -> dict[str, Any]:
    import subprocess

    return {
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "dirty_paths": subprocess.run(
            ["git", "status", "--short"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines(),
        "file_sha256": {name: _sha256_file(ROOT / name) for name in SOURCE_FILES},
    }


def _actual_mesh_identity(mesh, space) -> dict[str, np.ndarray]:
    topology_dimension = int(mesh.topology.dim)
    mesh.topology.create_connectivity(topology_dimension, 0)
    cell_connectivity = mesh.topology.connectivity(topology_dimension, 0)
    if cell_connectivity is None:
        raise RuntimeError("rebuilt mesh has no cell-to-vertex connectivity")
    cell_map = mesh.topology.index_map(topology_dimension)
    cell_ids = cell_map.local_to_global(np.arange(cell_map.size_local, dtype=np.int32))
    dof_index_map = space.dofmap.index_map
    owned_dof_ids = dof_index_map.local_to_global(
        np.arange(dof_index_map.size_local, dtype=np.int32)
    )
    return {
        "mesh_geometry_coordinates_nm": np.asarray(mesh.geometry.x).copy(),
        "mesh_geometry_dofmap": np.asarray(mesh.geometry.dofmap).copy(),
        "mesh_owned_cell_global_ids": np.asarray(cell_ids, dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.asarray(cell_connectivity.array).copy(),
        "p6_function_space_cell_dofmap": np.asarray(space.dofmap.list).copy(),
        "p6_owned_global_dof_block_ids": np.asarray(owned_dof_ids, dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray(
            dof_index_map.ghosts, dtype=np.int64
        ).copy(),
    }


def _axes_from_mesh(mesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int64)
    coordinates = np.asarray(mesh.geometry.x[:, :3], dtype=np.float64)
    return tuple(
        np.unique(coordinates[np.unique(geometry_dofmap), axis])
        for axis in range(3)
    )  # type: ignore[return-value]


def _load_field_case(label: str, out_root: Path):
    if label == "current_180":
        record_path = CURRENT_RUN / "task43_initial180_current_record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("gates", {}).get("pass") is not True:
            raise ValueError("frozen current does not have a passing hard-gate record")
        storage_path = CURRENT_RUN / "recovered_solution_storage.npz"
        expected_storage_sha = str(record["recovered_solution_storage"]["sha256"])
        if _sha256_file(storage_path) != expected_storage_sha:
            raise ValueError("current recovered storage does not match its record hash")
        cfg = _h100_config(
            kind="empty_h_active_p3",
            case_name="task43_initial180_current_active_p3_initial180_mpi1",
            geometry_profile="initial_180",
        )
        plan_path = CURRENT_RUN / "empty_h_active_p3_plan.json"
        expected_plan_sha = str(
            record["numerical_controls"]["local_h_empty_plan"]["plan_sha256"]
        )
        if _sha256_file(plan_path) != expected_plan_sha:
            raise ValueError("current empty-h plan differs from its recorded hash")
        cfg.stage4_local_h_refinement_plan = str(plan_path)
        mesh_data = build_stage4_local_h_mesh_data(
            cfg,
            plan_path,
            comm=MPI.COMM_WORLD,
        )
        archive = np.load(storage_path, allow_pickle=False)
        coefficients = np.asarray(
            archive["recovered_p6_local_coefficients"], dtype=np.complex128
        ).copy()
        expected_arrays = {
            key: np.asarray(archive[source_key]).copy()
            for key, source_key in zip(
                _IDENTITY_ARRAYS,
                (
                    "mesh_geometry_coordinates_nm",
                    "mesh_geometry_dofmap",
                    "mesh_owned_cell_global_ids",
                    "mesh_cell_vertex_dofmap",
                    "p6_function_space_dofmap",
                    "p6_owned_global_dof_block_ids",
                    "p6_ghost_global_dof_block_ids",
                ),
                strict=True,
            )
        }
        # Keep the current mode/output record bound to the same solve artifact.
        modes_path = CURRENT_RUN / "solve/dtn_port_diffraction_orders_3d.json"
        modes_sha = _sha256_file(modes_path)
        expected_modes_sha = str(record["power"]["channel_rows_sha256"])
        if modes_sha != expected_modes_sha:
            raise ValueError("current ordered mode rows differ from the recorded hash")
        with modes_path.open(encoding="utf-8") as stream:
            mode_payload = json.load(stream)
        return label, cfg, mesh_data, coefficients, expected_arrays, record, mode_payload

    if label not in {"Y6_1", "Y6_2"}:
        raise ValueError("only current_180, Y6_1 and Y6_2 are allowed")
    case_root = REFERENCE_ROOT / label
    record = json.loads((case_root / "restore_identity_record.json").read_text())
    if record.get("status") != "RESTORATION_IDENTITY_PASS_NOT_TASK43_QUALIFIED":
        raise ValueError(f"{label} does not have the expected restoration-only status")
    bundle_path = case_root / "recovered_reference_bundle.npz"
    if _sha256_file(bundle_path) != record["recovered_bundle"]["sha256"]:
        raise ValueError(f"{label} recovered bundle differs from its identity record")
    with np.load(bundle_path, allow_pickle=False) as archive:
        coefficients = np.asarray(
            archive["recovered_full_local_coefficients"], dtype=np.complex128
        ).copy()
        expected_arrays = {
            key: np.asarray(archive[archive_key]).copy()
            for key, archive_key in zip(
                _IDENTITY_ARRAYS,
                (
                    "mesh_geometry_coordinates_nm",
                    "mesh_geometry_dofmap",
                    "mesh_owned_cell_global_ids",
                    "mesh_cell_vertex_dofmap",
                    "p6_function_space_cell_dofmap",
                    "p6_owned_global_dof_block_ids",
                    "p6_ghost_global_dof_block_ids",
                ),
                strict=True,
            )
        }
    config_path = case_root / "resolved_config.json"
    expected_config_sha = str(
        record["input_artifacts"]["resolved_config.json"]["sha256"]
    )
    if _sha256_file(config_path) != expected_config_sha:
        raise ValueError(f"{label} copied config differs from its restoration record")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    inventory = _load_inventory_entry(label)
    cfg = _configure_historical_direct_route(config, inventory)
    mesh_data = build_airbox_mesh_3d(cfg, out_root / f"mesh_{label}")
    orders_path = case_root / "numerical_output/dtn_port_diffraction_orders_3d.json"
    expected_orders_sha = str(
        record["input_artifacts"][
            "numerical_output/dtn_port_diffraction_orders_3d.json"
        ]["sha256"]
    )
    if _sha256_file(orders_path) != expected_orders_sha:
        raise ValueError(f"{label} copied mode rows differ from their restoration record")
    mode_payload = json.loads(orders_path.read_text(encoding="utf-8"))
    return label, cfg, mesh_data, coefficients, expected_arrays, record, mode_payload


def _cell_slot_for_points(mesh, axes, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map common points to actual leaves, including coarse union-axis cells."""

    cell_map = mesh.topology.index_map(mesh.topology.dim)
    owned = int(cell_map.size_local)
    if cell_map.size_global != owned:
        raise RuntimeError("point-to-cell attribution currently requires a serial mesh")
    global_ids = np.asarray(
        cell_map.local_to_global(np.arange(owned, dtype=np.int32)), dtype=np.int64
    )
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int64)
    coordinates = np.asarray(mesh.geometry.x[:, :3], dtype=np.float64)
    cell_vertices = coordinates[geometry_dofmap[:owned]]
    bounds = np.stack((cell_vertices.min(axis=1), cell_vertices.max(axis=1)), axis=1)
    local_cell_ids = attribute_points_to_axis_aligned_cells(points, axes, bounds)
    return global_ids, local_cell_ids


def _complex_pair(value: Any) -> complex:
    return complex(float(value[0]), float(value[1]))


def _mode_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))


def _modal_identity(mode_payload: dict[str, Any], label: str) -> tuple[list[tuple[str, int, int, str]], np.ndarray, list[dict[str, Any]]]:
    rows = mode_payload["orders"]
    keys = [_mode_key(row) for row in rows]
    amplitudes = np.asarray(
        [_complex_pair(row["outgoing_amplitude_at_boundary"]) for row in rows],
        dtype=np.complex128,
    )
    return keys, amplitudes, rows


def _modal_comparison(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    ref_keys, ref_amplitudes, ref_rows = _modal_identity(reference["mode_payload"], reference["label"])
    cand_keys, cand_amplitudes, cand_rows = _modal_identity(candidate["mode_payload"], candidate["label"])
    if ref_keys != cand_keys or len(ref_keys) != 612:
        raise ValueError("ordered R13 modal identities differ or do not contain 612 entries")
    channel_power_ratio_difference = np.empty(612, dtype=np.float64)
    for index, (ref_row, cand_row) in enumerate(zip(ref_rows, cand_rows, strict=True)):
        channel_power_ratio_difference[index] = abs(
            float(cand_row["power_ratio"]) - float(ref_row["power_ratio"])
        )
    amplitude_delta = cand_amplitudes - ref_amplitudes
    groups: dict[str, Any] = {}
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            label = f"{side}_{polarization}"
            indices = np.asarray(
                [i for i, key in enumerate(ref_keys) if key[0] == side and key[3] == polarization],
                dtype=np.int64,
            )
            ref_norm = float(np.linalg.norm(ref_amplitudes[indices]))
            difference_norm = float(np.linalg.norm(amplitude_delta[indices]))
            groups[label] = {
                "mode_count": int(indices.size),
                "reference_boundary_amplitude_l2": ref_norm,
                "difference_boundary_amplitude_l2": difference_norm,
                "relative_to_reference": difference_norm / ref_norm if ref_norm else None,
                "relative_with_unit_incident_modal_floor": difference_norm / max(ref_norm, 1.0),
            }
    ref_power = reference["power"]
    cand_power = candidate["power"]
    power_differences = {
        key: abs(float(cand_power[key]) - float(ref_power[key]))
        for key in ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")
    }
    maximum_index = int(np.argmax(channel_power_ratio_difference))
    return {
        "reference_label": reference["label"],
        "candidate_label": candidate["label"],
        "ordered_mode_count": len(ref_keys),
        "ordered_mode_keys_sha256": hashlib.sha256(
            json.dumps(ref_keys, separators=(",", ":")).encode("ascii")
        ).hexdigest(),
        "power_absolute_differences": power_differences,
        "maximum_individual_channel_power_ratio_absolute_difference": float(channel_power_ratio_difference[maximum_index]),
        "maximum_individual_channel_power_ratio_key": list(ref_keys[maximum_index]),
        "individual_channel_power_ratio_absolute_difference_l2": float(np.linalg.norm(channel_power_ratio_difference)),
        "individual_channel_power_ratio_absolute_differences": channel_power_ratio_difference.tolist(),
        "boundary_amplitude_vector_absolute_l2_difference": float(np.linalg.norm(amplitude_delta)),
        "boundary_amplitude_vector_max_abs_difference": float(np.max(np.abs(amplitude_delta))),
        "boundary_amplitude_groups": groups,
        "phase_fit": False,
    }


def _complex_components(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _physical_configuration_identity(cfg) -> dict[str, Any]:
    serialized = cfg.as_jsonable()
    wavevector = np.asarray(cfg.wavevector, dtype=np.complex128)
    polarization = np.asarray(cfg.polarization_vector, dtype=np.complex128)
    return {
        "exact": {
            "geometry_kind": str(cfg.geometry_kind),
            "scattering_background": str(cfg.scattering_background),
            "polarization_kind": str(cfg.polarization_kind),
            "electric_field_unit": str(serialized["electric_field_unit"]),
            "magnetic_field_unit": str(serialized["magnetic_field_unit"]),
        },
        "numeric": {
            "lambda0_nm": [float(cfg.lambda0)],
            "periods_nm": [float(cfg.period_x), float(cfg.period_y)],
            "physical_z_bounds_nm": [float(cfg.physical_z_min), float(cfg.physical_z_max)],
            "domain_z_bounds_nm": [float(cfg.domain_z_min), float(cfg.domain_z_max)],
            "grating_box_nm": [
                float(cfg.grating_x_min), float(cfg.grating_x_max),
                float(cfg.grating_y_min), float(cfg.grating_y_max),
                float(cfg.grating_z_min), float(cfg.grating_z_max),
            ],
            "interface_z_nm": [float(cfg.interface_z)],
            "layer_heights_nm": [float(cfg.air_height), float(cfg.substrate_thickness)],
            "incident_angles_deg": [float(cfg.incident_theta_deg), float(cfg.incident_phi_deg)],
            "incident_amplitude": _complex_components(cfg.incident_amplitude),
            "incident_e0_v_per_m": [float(cfg.incident_e0_v_per_m)],
            "n_air": _complex_components(cfg.n_air),
            "mu_r": _complex_components(cfg.mu_r),
            "n_substrate": _complex_components(cfg.substrate_index),
            "n_grating": _complex_components(cfg.grating_index),
            "eps_air": _complex_components(cfg.eps_air),
            "eps_substrate": _complex_components(cfg.eps_substrate),
            "eps_grating": _complex_components(cfg.eps_grating),
            "k0_per_nm": [float(cfg.k0)],
            "incident_wavevector": np.stack(
                (wavevector.real, wavevector.imag), axis=1
            ).ravel().tolist(),
            "incident_polarization": np.stack(
                (polarization.real, polarization.imag), axis=1
            ).ravel().tolist(),
            "magnetic_field_scale_a_per_m": [
                float(cfg.magnetic_field_scale_A_per_m)
            ],
        },
    }


def _validate_common_physics(cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    labels = ("current_180", "Y6_1", "Y6_2")
    baseline = _physical_configuration_identity(cases[labels[0]]["cfg"])
    numeric_differences: dict[str, dict[str, float]] = {}
    for label in labels:
        cfg = cases[label]["cfg"]
        identity = _physical_configuration_identity(cfg)
        if identity["exact"] != baseline["exact"]:
            raise ValueError(f"{label} physical configuration labels differ from current")
        if identity["numeric"].keys() != baseline["numeric"].keys():
            raise RuntimeError("physical-configuration identity fields are inconsistent")
        numeric_differences[label] = {}
        for name, expected in baseline["numeric"].items():
            actual_array = np.asarray(identity["numeric"][name], dtype=np.float64)
            expected_array = np.asarray(expected, dtype=np.float64)
            difference = float(np.max(np.abs(actual_array - expected_array)))
            numeric_differences[label][name] = difference
            if not np.allclose(actual_array, expected_array, rtol=1.0e-12, atol=1.0e-14):
                raise ValueError(f"{label} {name} differs from the frozen current physics")

    current = cases["current_180"]["cfg"]
    volume = float(current.period_x * current.period_y * (current.domain_z_max - current.domain_z_min))
    if (
        abs(complex(current.n_air) - 1.0) > 1.0e-14
        or abs(complex(current.mu_r) - 1.0) > 1.0e-14
        or abs(complex(current.incident_amplitude) - 1.0) > 1.0e-14
        or abs(float(current.incident_e0_v_per_m) - 1.0) > 1.0e-14
        or abs(volume - 350000.0) > 1.0e-8
    ):
        raise ValueError("the fixed unit-incident sqrt(700000) norm floor is not valid for this model")
    return {
        "shared_identity": baseline,
        "maximum_absolute_differences_by_case": numeric_differences,
        "unit_incident_plane_wave_verified": True,
        "n_air_one_verified": True,
        "mu_r_one_verified": True,
        "domain_volume_nm3": volume,
        "incident_g_norm_floor": float(np.sqrt(2.0 * volume)),
    }


def _validate_mode_physics(cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fields = ("alpha", "gamma", "beta", "kz", "refractive_index")
    flags = ("direction", "medium", "vertical_sign", "propagating", "power_carrying")
    baseline_rows = cases["current_180"]["mode_payload"]["orders"]
    differences: dict[str, dict[str, float]] = {}
    for label in ("Y6_1", "Y6_2"):
        rows = cases[label]["mode_payload"]["orders"]
        if len(rows) != len(baseline_rows):
            raise ValueError(f"{label} modal inventory length differs from current")
        differences[label] = {}
        for index, (current_row, reference_row) in enumerate(
            zip(baseline_rows, rows, strict=True)
        ):
            if _mode_key(current_row) != _mode_key(reference_row):
                raise ValueError(f"{label} ordered modal key differs at row {index}")
            for name in flags:
                if current_row[name] != reference_row[name]:
                    raise ValueError(f"{label} modal {name} differs at row {index}")
            for name in fields:
                current_value = np.asarray(_complex_pair(current_row[name]), dtype=np.complex128)
                reference_value = np.asarray(_complex_pair(reference_row[name]), dtype=np.complex128)
                difference = float(np.max(np.abs(current_value - reference_value)))
                differences[label][name] = max(differences[label].get(name, 0.0), difference)
                if not np.allclose(current_value, reference_value, rtol=1.0e-12, atol=1.0e-14):
                    raise ValueError(f"{label} modal {name} differs at row {index}")
    return {
        "physics_row_fields_checked": [*fields, *flags],
        "boundary_phase_excluded_from_basis_identity": (
            "Task43 uses boundary_magnitude_scaled_r5_v1 while historical modes use the unscaled Task40 gauge; "
            "comparison uses outgoing_amplitude_at_boundary instead."
        ),
        "maximum_absolute_complex_differences": differences,
    }


def _validate_recorded_quadrature_and_cutoff(
    cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    current_controls = cases["current_180"]["record"]["numerical_controls"]
    expected = {
        "volume_degree": 15,
        "surface_and_incident_degree": 28,
        "volume_rule": "default",
        "cutoff_policy": "scale_homogeneous_relative_only_v1",
        "cutoff_relative_tolerance": 1.0e-13,
    }
    current = {
        "volume_degree": current_controls["volume_quadrature_degree"],
        "surface_and_incident_degree": current_controls[
            "incident_and_port_quadrature_degree"
        ],
        "volume_rule": current_controls["volume_quadrature_rule"],
        "cutoff_policy": current_controls["sparse_cutoff_policy"],
        "cutoff_relative_tolerance": current_controls[
            "sparse_cutoff_relative_tolerance"
        ],
    }
    if current != expected:
        raise ValueError("current numerical integration/cutoff differs from Task43 profile")
    reference_records: dict[str, Any] = {}
    for label in ("Y6_1", "Y6_2"):
        resolved = cases[label]["record"]["resolved_identity"][
            "quadrature_and_cutoff"
        ]
        identity = {
            "volume_degree": resolved["volume_degree"],
            "surface_and_incident_degree": resolved[
                "surface_and_incident_degree"
            ],
            "volume_rule": resolved["volume_rule"],
            "cutoff_policy": resolved["cutoff_policy"],
            "cutoff_relative_tolerance": resolved["cutoff_relative_tolerance"],
        }
        if identity != expected:
            raise ValueError(f"{label} recorded q/cutoff differs from Task43 profile")
        reference_records[label] = identity
    return {"expected": expected, "current": current, "references": reference_records}


def _scalar_power_record(label: str, case_record: dict[str, Any], mode_payload: dict[str, Any]) -> dict[str, float]:
    if label == "current_180":
        aggregate = case_record["power"]["aggregate"]
        return {
            "R_total": float(aggregate["R_total"]),
            "T_total": float(aggregate["T_total"]),
            "A_volume": float(case_record["power"]["A_volume_total"]),
            "R00_s": float(aggregate["R00_s"]),
            "R00_p": float(aggregate["R00_p"]),
            "R00_total": float(aggregate["R00_total"]),
        }
    historical = case_record["resolved_identity"]["historical_power_diagnostic"]
    rows = mode_payload["orders"]
    r00_s = sum(float(row["R"]) for row in rows if row["side"] == "top" and row["m"] == 0 and row["n"] == 0 and row["polarization"] == "s")
    r00_p = sum(float(row["R"]) for row in rows if row["side"] == "top" and row["m"] == 0 and row["n"] == 0 and row["polarization"] == "p")
    return {
        "R_total": float(historical["R"]),
        "T_total": float(historical["T"]),
        "A_volume": float(historical["A_volume"]),
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_s + r00_p,
    }


def _field_metrics(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
    points: np.ndarray,
    weights: np.ndarray,
    cfg,
) -> dict[str, Any]:
    background_e = electric_field_code_values(cfg, points)
    background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(cfg, points)
    ref_h = magnetic_field_from_electric_curl(
        reference["curl_E"],
        magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
        k0_per_nm=cfg.k0,
        mu_r=cfg.mu_r,
    )
    cand_h = magnetic_field_from_electric_curl(
        candidate["curl_E"],
        magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
        k0_per_nm=cfg.k0,
        mu_r=cfg.mu_r,
    )
    volume = float(cfg.period_x * cfg.period_y * (cfg.domain_z_max - cfg.domain_z_min))
    e_floor = float(np.sqrt(volume))
    h_floor = e_floor * float(cfg.magnetic_field_scale_A_per_m)
    ref_e_scattered = scattered_field_samples(reference["E"], background_e)
    cand_e_scattered = scattered_field_samples(candidate["E"], background_e)
    ref_h_scattered = scattered_field_samples(ref_h, background_h)
    cand_h_scattered = scattered_field_samples(cand_h, background_h)
    g_metrics = physical_g_difference_metrics(
        reference["E"],
        candidate["E"],
        reference["curl_E"],
        candidate["curl_E"],
        weights,
        k0_per_nm=cfg.k0,
        incident_g_norm_floor=float(np.sqrt(2.0 * volume)),
    )
    return {
        "E_total_code": weighted_vector_field_metrics(
            reference["E"], candidate["E"], weights, reference_norm_floor=e_floor
        ),
        "curl_E_over_k0_code": weighted_vector_field_metrics(
            reference["curl_E"] / cfg.k0,
            candidate["curl_E"] / cfg.k0,
            weights,
            reference_norm_floor=e_floor,
        ),
        "H_total_A_per_m": weighted_vector_field_metrics(
            ref_h, cand_h, weights, reference_norm_floor=h_floor
        ),
        "E_scattered_code": weighted_vector_field_metrics(
            ref_e_scattered, cand_e_scattered, weights, reference_norm_floor=e_floor
        ),
        "H_scattered_A_per_m": weighted_vector_field_metrics(
            ref_h_scattered, cand_h_scattered, weights, reference_norm_floor=h_floor
        ),
        "G": g_metrics,
    }


def compare(output_root: Path) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("shared field comparison is currently qualified for MPI1 only")
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite comparison attempt: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    source_identity_start = _source_snapshot()
    (output_root / "source_identity_start.json").write_text(
        json.dumps(source_identity_start, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"stage": "begin", "output": str(output_root)}), flush=True)

    cases: dict[str, dict[str, Any]] = {}
    for label in ("current_180", "Y6_1", "Y6_2"):
        case_started = time.perf_counter()
        loaded = _load_field_case(label, output_root)
        label, cfg, mesh_data, coefficients, expected_arrays, record, mode_payload = loaded
        mesh = mesh_data.mesh
        if mesh.comm.size != 1:
            raise RuntimeError(f"{label} reconstructed mesh is not serial")
        space = _create_nedelec_space(mesh, cfg)
        actual_arrays = _actual_mesh_identity(mesh, space)
        for name in _IDENTITY_ARRAYS:
            if not np.array_equal(actual_arrays[name], expected_arrays[name]):
                raise ValueError(f"{label} reconstructed {name} differs from stored field identity")
        field = fem.Function(space, name=f"{label}_full_recovered_E")
        if field.x.array.shape != coefficients.shape:
            raise ValueError(f"{label} coefficient shape differs from reconstructed full field")
        field.x.array[:] = coefficients
        field.x.scatter_forward()
        axes = _axes_from_mesh(mesh)
        if coefficients.size != space.dofmap.index_map.size_local + space.dofmap.index_map.num_ghosts:
            raise ValueError(f"{label} coefficient vector is not the complete local function vector")
        cases[label] = {
            "label": label,
            "cfg": cfg,
            "mesh_data": mesh_data,
            "space": space,
            "field": field,
            "axes": axes,
            "record": record,
            "mode_payload": mode_payload,
            "power": _scalar_power_record(label, record, mode_payload),
            "mesh_identity": {name: _array_identity(values) for name, values in actual_arrays.items()},
        }
        print(
            json.dumps(
                {
                    "stage": "field_identity_verified",
                    "label": label,
                    "cell_count": int(mesh.topology.index_map(mesh.topology.dim).size_global),
                    "field_dofs": int(coefficients.size),
                    "axes_shape": [len(axis) for axis in axes],
                    "seconds": time.perf_counter() - case_started,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    common_physics = _validate_common_physics(cases)
    modal_physics = _validate_mode_physics(cases)
    integration_identity = _validate_recorded_quadrature_and_cutoff(cases)
    common_axes = tuple(
        np.unique(np.concatenate([cases[label]["axes"][axis] for label in cases]))
        for axis in range(3)
    )
    cases["current_180"]["common_axes"] = common_axes
    current_mesh = cases["current_180"]["mesh_data"].mesh
    current_cell_global_ids, _ = _cell_slot_for_points(
        current_mesh,
        cases["current_180"]["axes"],
        np.asarray([[(common_axes[0][0] + common_axes[0][1]) * 0.5,
                     (common_axes[1][0] + common_axes[1][1]) * 0.5,
                     (common_axes[2][0] + common_axes[2][1]) * 0.5]],
                   dtype=np.float64),
    )
    reference_mode_payloads = {
        label: cases[label]["mode_payload"] for label in ("Y6_1", "Y6_2")
    }
    modal_outputs: dict[str, Any] = {}
    for reference_label in ("Y6_1", "Y6_2"):
        modal_outputs[reference_label] = _modal_comparison(
            {**cases[reference_label], "mode_payload": reference_mode_payloads[reference_label]},
            cases["current_180"],
        )
    modal_outputs["Y6_1_vs_Y6_2"] = _modal_comparison(
        cases["Y6_1"], cases["Y6_2"]
    )

    # Verify all restored and current modes carry the same ordered R13 identities.
    current_rows = cases["current_180"]["mode_payload"]["orders"]
    current_keys = [_mode_key(row) for row in current_rows]
    for label in ("Y6_1", "Y6_2"):
        reference_keys, _amp, _rows = _modal_identity(cases[label]["mode_payload"], label)
        if current_keys != reference_keys:
            raise ValueError(f"current and {label} mode identities/order differ")
    mode_metrics_by_label = {
        label: cases[label]["mode_payload"]["metrics"]
        for label in ("current_180", "Y6_1", "Y6_2")
    }
    for label in ("current_180", "Y6_1", "Y6_2"):
        metrics = mode_metrics_by_label[label]
        mode_count = metrics.get("active_mode_count", metrics.get("dtn_port_mode_count"))
        if mode_count != 612:
            raise ValueError(f"{label} stored modal output is not complete R13")

    field_metrics: dict[str, Any] = {}
    quadrature_identities: dict[str, Any] = {}
    contributions_by_order: dict[int, np.ndarray] = {}
    marking_by_order: dict[int, dict[str, Any]] = {}
    marked_ids_by_order: dict[int, np.ndarray] = {}
    closure_by_order: dict[int, float] = {}
    for order in (8, 10):
        q_started = time.perf_counter()
        quadrature = build_common_volume_quadrature(
            [cases[label]["axes"] for label in ("current_180", "Y6_1", "Y6_2")],
            gauss_order=order,
        )
        if abs(float(np.sum(quadrature.weights_nm3)) - 350000.0) > 1.0e-8:
            raise ValueError("shared volume rule does not integrate the fixed physical domain volume")
        current_global_ids, point_cell_slots = _cell_slot_for_points(
            current_mesh,
            cases["current_180"]["axes"],
            quadrature.points_nm,
        )
        if not np.array_equal(current_global_ids, current_cell_global_ids):
            raise RuntimeError("current cell global IDs changed across shared integration rules")
        sampled: dict[str, dict[str, np.ndarray]] = {}
        for label in ("current_180", "Y6_1", "Y6_2"):
            export = prepare_cell_local_vector_field_export(cases[label]["field"])
            values = sample_cell_local_vector_fields(
                {
                    "E": export.electric_dgq6,
                    "curl_E": export.curl_electric_dgq6,
                },
                quadrature.points_nm,
                batch_size=32768,
            )
            if values is None:
                raise RuntimeError("MPI1 sampler returned no root field values")
            sampled[label] = values
            print(
                json.dumps(
                    {
                        "stage": "shared_field_sampled",
                        "label": label,
                        "gauss_order": order,
                        "sample_count": len(quadrature.weights_nm3),
                        "seconds": time.perf_counter() - q_started,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

        field_metrics[f"q{order}"] = {
            "current_vs_Y6_1": _field_metrics(
                sampled["Y6_1"], sampled["current_180"], quadrature.points_nm,
                quadrature.weights_nm3, cases["current_180"]["cfg"],
            ),
            "current_vs_Y6_2": _field_metrics(
                sampled["Y6_2"], sampled["current_180"], quadrature.points_nm,
                quadrature.weights_nm3, cases["current_180"]["cfg"],
            ),
            "Y6_1_vs_Y6_2": _field_metrics(
                sampled["Y6_1"], sampled["Y6_2"], quadrature.points_nm,
                quadrature.weights_nm3, cases["current_180"]["cfg"],
            ),
        }
        contributions = accumulate_physical_g_cell_contributions(
            sampled["Y6_1"]["E"], sampled["current_180"]["E"],
            sampled["Y6_1"]["curl_E"], sampled["current_180"]["curl_E"],
            quadrature.weights_nm3, point_cell_slots,
            cell_global_ids=current_global_ids,
            k0_per_nm=cases["current_180"]["cfg"].k0,
        )
        marked_ids, marking = dorfler_mark_physical_g(
            current_global_ids, contributions, theta=0.5
        )
        metric_bundle = field_metrics[f"q{order}"]["current_vs_Y6_1"]["G"]
        contribution_sum = float(np.sum(contributions, dtype=np.float64))
        expected_difference_squared = float(metric_bundle["difference_g_norm"]) ** 2
        closure = abs(contribution_sum - expected_difference_squared) / max(
            expected_difference_squared, 1.0e-300
        )
        if closure > 2.0e-12:
            raise ValueError(f"q{order} current-leaf G contributions do not close to the full-volume norm")
        contributions_by_order[order] = contributions
        marking_by_order[order] = marking
        marked_ids_by_order[order] = marked_ids
        closure_by_order[order] = closure
        field_metrics[f"q{order}"]["current_vs_Y6_1"]["G_cell_contributions"] = {
            "cell_global_ids": current_global_ids.tolist(),
            "cell_g_error_squared": contributions.tolist(),
            "marked_global_cell_ids": marked_ids.tolist(),
            "marking": marking,
            "sum_vs_full_volume_g_difference_relative_closure": closure,
        }
        sample_path = output_root / f"shared_volume_samples_q{order}.npz"
        arrays: dict[str, np.ndarray] = {
            "points_nm": quadrature.points_nm,
            "weights_nm3": quadrature.weights_nm3,
            "current_cell_global_ids": current_global_ids,
            "point_current_cell_local_slots": point_cell_slots,
        }
        for label in ("current_180", "Y6_1", "Y6_2"):
            arrays[f"{label}_E_code"] = sampled[label]["E"]
            arrays[f"{label}_curl_E_code"] = sampled[label]["curl_E"]
        np.savez_compressed(sample_path, **arrays)
        quadrature_identities[f"q{order}"] = {
            "gauss_order_per_axis_per_interval": order,
            "shared_interval_count": int(np.prod([len(axis) - 1 for axis in quadrature.axis_breakpoints_nm])),
            "sample_count": int(quadrature.weights_nm3.size),
            "integrated_domain_volume_nm3": float(np.sum(quadrature.weights_nm3)),
            "axis_breakpoints_nm": [axis.tolist() for axis in quadrature.axis_breakpoints_nm],
            "rule_sha256": quadrature.rule_sha256,
            "sample_bundle": str(sample_path),
            "sample_bundle_sha256": _sha256_file(sample_path),
        }
        print(
            json.dumps(
                {"stage": "quadrature_complete", "gauss_order": order,
                 "sample_count": int(quadrature.weights_nm3.size),
                 "seconds": time.perf_counter() - q_started},
                sort_keys=True,
            ),
            flush=True,
        )

    output_difference_record = {
        "current_180_vs_Y6_1": modal_outputs["Y6_1"],
        "current_180_vs_Y6_2": modal_outputs["Y6_2"],
        "Y6_1_vs_Y6_2_reference_disagreement": modal_outputs["Y6_1_vs_Y6_2"],
    }
    source_identity_end = _source_snapshot()
    source_unchanged = (
        source_identity_start["git_head"] == source_identity_end["git_head"]
        and source_identity_start["file_sha256"] == source_identity_end["file_sha256"]
    )
    if not source_unchanged:
        failure_identity = {
            "source_identity_start": source_identity_start,
            "source_identity_end": source_identity_end,
        }
        (output_root / "source_identity_failure.json").write_text(
            json.dumps(failure_identity, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("Task43 comparison source changed while fields were being evaluated")

    dorfler_records: dict[str, Any] = {}
    for order in (8, 10):
        metric_bundle = field_metrics[f"q{order}"]["current_vs_Y6_1"]["G"]
        contribution_sum = float(
            np.sum(contributions_by_order[order], dtype=np.float64)
        )
        dorfler_records[f"q{order}"] = {
            "theta": 0.5,
            "marked_global_cell_ids": marked_ids_by_order[order].tolist(),
            "marking": marking_by_order[order],
            "total_g_error_norm": float(np.sqrt(contribution_sum)),
            "sum_vs_full_volume_g_difference_relative_closure": closure_by_order[order],
            "classification": "measured_selection_indicator_not_a_continuum_error",
        }
    record = {
        "schema": "task43.reference-calibration.v1",
        "classification": "measured_reference_pair_disagreement_and_current_field_difference_not_accuracy_acceptance",
        "reference_roles": {"selection": "Y6_1", "calibration": "Y6_2", "holdout": "Y5_1_not_read"},
        "current_case": "frozen_180_cell_active_p3_current",
        "source_identity": {
            "start": source_identity_start,
            "end": source_identity_end,
            "unchanged_during_comparison": source_unchanged,
        },
        "method": {
            "field_representation": "recovered N1curl p6 carrier evaluated via exact cell-local DGQ6 E and curl(E)",
            "integration": "tensor Gauss on the union of all three actual mesh breakpoint axes",
            "quadrature_orders": [8, 10],
            "G_definition": "integral(|E|^2 + |curl(E)|^2/k0^2) dV",
            "G_relative_floor": "sqrt(700000) from unit incident plane wave over the fixed 350000 nm^3 domain",
            "H_definition": "physical H recovered from curl(E) using resolved cfg units",
            "scattered_background": "the same analytic flat air/substrate Fresnel E/H evaluated at common points",
            "phase_fit": False,
            "current_leaf_attribution": "q8 and q10 samples mapped by actual axis-aligned leaf boxes onto the shared Cartesian interval lattice; coarse leaves cover multiple union-axis intervals",
            "selection_rule": "Dörfler theta=0.5 on per-leaf integral of |delta E|^2+|delta curl(E)/k0|^2; no candidate accepted yet",
        },
        "physical_configuration_identity": common_physics,
        "modal_physics_identity": modal_physics,
        "recorded_quadrature_and_cutoff_identity": integration_identity,
        "quadrature": quadrature_identities,
        "field_differences": field_metrics,
        "modal_and_power_differences": output_difference_record,
        "dorfler_by_quadrature": dorfler_records,
        "qualifications_not_claimed": [
            "Y6_1/Y6_2 are not fully independently residual-recomputed here; their recorded original residuals and restore identity were checked separately.",
            "The selected references are finite discrete fields and do not establish continuum convergence.",
            "Four vertical one-sided sidewall traces remain outside this volume comparison.",
            "The 6x10x6 p6 control remains excluded from marking and ranking.",
            "No p/h candidate solve or accepted update is included in this record.",
        ],
        "status": "REFERENCE_PAIR_FIELD_AND_MODAL_COMPARISON_COMPLETE_CANDIDATE_RUNS_PENDING",
        "wall_seconds": time.perf_counter() - started,
    }
    record_path = output_root / "reference_calibration_v1.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"stage": "comparison_complete", "status": record["status"],
             "record": str(record_path), "wall_seconds": record["wall_seconds"]},
            sort_keys=True,
        ),
        flush=True,
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", default="attempt1")
    args = parser.parse_args()
    output_root = DEFAULT_OUTPUT_ROOT / args.attempt_id
    if not args.attempt_id or Path(args.attempt_id).name != args.attempt_id:
        parser.error("--attempt-id must be one path component")
    compare(output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
