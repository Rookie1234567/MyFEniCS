"""Formal fixed-target Task035b regionwise-p candidate execution."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _complex(values: list[float]) -> complex:
    return complex(float(values[0]), float(values[1]))


def _channel_key(entry: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(entry["side"]),
        int(entry["m"]),
        int(entry["n"]),
        str(entry["polarization"]),
    )


def _load_channel_file(path: Path) -> dict[tuple[str, int, int, str], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload["orders"] if isinstance(payload, dict) else payload
    return {_channel_key(entry): entry for entry in entries}


def _channel_comparison(
    *,
    p5_dir: Path,
    p6_dir: Path,
    candidate_dir: Path,
    significant_power_floor: float = 1.0e-8,
) -> dict[str, Any]:
    filename = "dtn_port_diffraction_orders_3d.json"
    p5 = _load_channel_file(p5_dir / filename)
    p6 = _load_channel_file(p6_dir / filename)
    candidate = _load_channel_file(candidate_dir / filename)
    if set(p5) != set(p6) or set(p6) != set(candidate):
        raise RuntimeError(
            "p5, p6, and regionwise-p diffraction channel identities differ"
        )
    rows: list[dict[str, Any]] = []
    power_gate_pass = True
    amplitude_gate_pass = True
    for key in sorted(p6):
        p5_entry = p5[key]
        p6_entry = p6[key]
        candidate_entry = candidate[key]
        p5_power = float(p5_entry["power_ratio"])
        p6_power = float(p6_entry["power_ratio"])
        candidate_power = float(candidate_entry["power_ratio"])
        p5_amplitude = _complex(p5_entry["outgoing_amplitude_at_boundary"])
        p6_amplitude = _complex(p6_entry["outgoing_amplitude_at_boundary"])
        candidate_amplitude = _complex(
            candidate_entry["outgoing_amplitude_at_boundary"]
        )
        significant = max(p5_power, p6_power) >= significant_power_floor
        power_tolerance = max(abs(p6_power - p5_power), 1.0e-12)
        amplitude_tolerance = max(
            abs(p6_amplitude - p5_amplitude),
            1.0e-10,
        )
        power_error = abs(candidate_power - p6_power)
        amplitude_error = abs(candidate_amplitude - p6_amplitude)
        if significant:
            power_gate_pass &= power_error <= power_tolerance
            amplitude_gate_pass &= amplitude_error <= amplitude_tolerance
        rows.append(
            {
                "side": key[0],
                "m": key[1],
                "n": key[2],
                "polarization": key[3],
                "significant": significant,
                "p5_power_ratio": p5_power,
                "p6_power_ratio": p6_power,
                "candidate_power_ratio": candidate_power,
                "candidate_vs_p6_power_absolute_error": power_error,
                "same_code_p5p6_power_tolerance": power_tolerance,
                "p5_outgoing_amplitude_at_boundary": [
                    p5_amplitude.real,
                    p5_amplitude.imag,
                ],
                "p6_outgoing_amplitude_at_boundary": [
                    p6_amplitude.real,
                    p6_amplitude.imag,
                ],
                "candidate_outgoing_amplitude_at_boundary": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "candidate_vs_p6_amplitude_absolute_error": amplitude_error,
                "same_code_p5p6_amplitude_tolerance": amplitude_tolerance,
            }
        )
    significant_rows = [row for row in rows if row["significant"]]
    return {
        "schema_version": "task035b.regionwise-p-channel-comparison.v1",
        "channel_count": len(rows),
        "significant_power_floor": significant_power_floor,
        "significant_channel_count": len(significant_rows),
        "same_code_band_definition": (
            "absolute p5-to-p6 channel change with explicit numerical floors"
        ),
        "significant_order_power_gate_pass": power_gate_pass,
        "significant_complex_amplitude_gate_pass": amplitude_gate_pass,
        "pass": power_gate_pass and amplitude_gate_pass,
        "channels": rows,
    }


def _observable_comparison(
    candidate: dict[str, Any],
    p5: dict[str, Any],
    p6: dict[str, Any],
) -> dict[str, Any]:
    values = {
        "R00_total": (
            float(candidate["R00_total"]),
            float(p5["R00_total"]),
            float(p6["R00_total"]),
        ),
        "R_total": (
            float(candidate["R_total"]),
            float(p5["R_total"]),
            float(p6["R_total"]),
        ),
        "T_total": (
            float(candidate["T_total"]),
            float(p5["T_total"]),
            float(p6["T_total"]),
        ),
        "A_closure": (
            1.0 - float(candidate["R_total"]) - float(candidate["T_total"]),
            1.0 - float(p5["R_total"]) - float(p5["T_total"]),
            1.0 - float(p6["R_total"]) - float(p6["T_total"]),
        ),
    }
    entries: dict[str, Any] = {}
    normalized_r_t_aclosure: list[float] = []
    for name, (candidate_value, p5_value, p6_value) in values.items():
        tolerance = max(abs(p6_value - p5_value), 1.0e-12)
        error = abs(candidate_value - p6_value)
        normalized_error = error / tolerance
        if name in {"R_total", "T_total", "A_closure"}:
            normalized_r_t_aclosure.append(normalized_error)
        entries[name] = {
            "candidate": candidate_value,
            "global_p5_control": p5_value,
            "global_p6_reference": p6_value,
            "candidate_vs_p6_absolute_error": error,
            "same_code_p5p6_tolerance": tolerance,
            "normalized_error": normalized_error,
            "pass": error <= tolerance,
        }
    normalized_l2 = math.sqrt(
        sum(value * value for value in normalized_r_t_aclosure)
    )
    normalized_reference_radius = math.sqrt(3.0)
    return {
        "schema_version": "task035b.regionwise-p-observable-comparison.v1",
        "same_code_band_definition": (
            "absolute p5-to-p6 change on the identical h10 mesh"
        ),
        "observables": entries,
        "normalized_R_T_Aclosure_l2": normalized_l2,
        "normalized_R_T_Aclosure_reference_radius": normalized_reference_radius,
        "normalized_R_T_Aclosure_vector_pass": (
            normalized_l2 <= normalized_reference_radius
        ),
        "all_scalar_same_code_bands_pass": all(
            entry["pass"] for entry in entries.values()
        ),
    }


def _selected_field_interface_comparison(
    *,
    p5_dir: Path,
    p6_dir: Path,
    candidate_dir: Path,
) -> dict[str, Any]:
    """Compare complex E on common native points, including material interfaces."""

    from mpi4py import MPI
    import numpy as np
    import pyvista as pv

    comm = MPI.COMM_WORLD
    rank_label = f"{comm.rank:04d}"
    filename = f"fields_3d_for_paraview_rank{rank_label}.vtu"
    paths = {
        "global_p5_control": p5_dir / filename,
        "global_p6_reference": p6_dir / filename,
        "regionwise_candidate": candidate_dir / filename,
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"{name} field shard is missing: {path}")
    grids = {name: pv.read(path) for name, path in paths.items()}

    def point_map(grid) -> dict[tuple[float, float, float], int]:
        return {
            tuple(float(value) for value in np.round(point, decimals=10)): index
            for index, point in enumerate(np.asarray(grid.points))
        }

    def complex_e(grid) -> Any:
        return np.asarray(grid.point_data["E_tot_V_per_m_real"]) + 1j * np.asarray(
            grid.point_data["E_tot_V_per_m_imag"]
        )

    maps = {name: point_map(grid) for name, grid in grids.items()}
    keys = set.intersection(*(set(mapping) for mapping in maps.values()))
    if not keys:
        raise RuntimeError("p5, p6, and candidate fields have no common native points")
    ordered_keys = sorted(keys)
    fields = {name: complex_e(grid) for name, grid in grids.items()}
    selected = {
        name: np.asarray(
            [field[maps[name][key]] for key in ordered_keys],
            dtype=np.complex128,
        )
        for name, field in fields.items()
    }
    coordinates = np.asarray(ordered_keys, dtype=np.float64)
    interface_z = 0.0
    grating_z_max = 120.0
    grating_x_min = 16.5
    grating_x_max = 33.5
    coordinate_tolerance = 1.0e-8
    z = coordinates[:, 2]
    x = coordinates[:, 0]
    in_grating_z = (
        (z >= interface_z - coordinate_tolerance)
        & (z <= grating_z_max + coordinate_tolerance)
    )
    in_grating_x = (
        (x >= grating_x_min - coordinate_tolerance)
        & (x <= grating_x_max + coordinate_tolerance)
    )
    interface_mask = (
        (np.abs(z - interface_z) <= coordinate_tolerance)
        | (
            (np.abs(z - grating_z_max) <= coordinate_tolerance)
            & in_grating_x
        )
        | (
            (
                (np.abs(x - grating_x_min) <= coordinate_tolerance)
                | (np.abs(x - grating_x_max) <= coordinate_tolerance)
            )
            & in_grating_z
        )
    )

    p5 = selected["global_p5_control"]
    p6 = selected["global_p6_reference"]
    candidate = selected["regionwise_candidate"]

    def local_accumulator(mask: Any) -> list[float]:
        reference = p6[mask]
        p5_delta = p5[mask] - reference
        candidate_delta = candidate[mask] - reference
        return [
            float(np.sum(np.abs(reference) ** 2)),
            float(np.sum(np.abs(p5_delta) ** 2)),
            float(np.sum(np.abs(candidate_delta) ** 2)),
            float(np.max(np.linalg.norm(p5_delta, axis=1), initial=0.0)),
            float(np.max(np.linalg.norm(candidate_delta, axis=1), initial=0.0)),
            float(np.count_nonzero(mask)),
        ]

    def global_metric(mask: Any) -> dict[str, Any]:
        local = local_accumulator(mask)
        sums = [
            float(comm.allreduce(local[index], op=MPI.SUM))
            for index in (0, 1, 2, 5)
        ]
        maxima = [
            float(comm.allreduce(local[index], op=MPI.MAX))
            for index in (3, 4)
        ]
        reference_norm = math.sqrt(sums[0])
        if reference_norm <= 0.0 or sums[3] <= 0.0:
            return {
                "selected_point_count": int(sums[3]),
                "pass": False,
                "reason": "empty selection or zero p6 reference norm",
            }
        p5_relative_l2 = math.sqrt(sums[1]) / reference_norm
        candidate_relative_l2 = math.sqrt(sums[2]) / reference_norm
        tolerance = max(p5_relative_l2, 1.0e-12)
        return {
            "selected_point_count": int(sums[3]),
            "global_p5_vs_p6_relative_l2": p5_relative_l2,
            "candidate_vs_p6_relative_l2": candidate_relative_l2,
            "same_code_p5p6_relative_l2_tolerance": tolerance,
            "global_p5_vs_p6_max_pointwise_absolute_error": maxima[0],
            "candidate_vs_p6_max_pointwise_absolute_error": maxima[1],
            "pass": candidate_relative_l2 <= tolerance,
        }

    shard_hashes = comm.allgather(
        {
            "rank": comm.rank,
            **{
                name: {
                    "path": str(path.resolve()),
                    "sha256": _sha256(path),
                }
                for name, path in paths.items()
            },
        }
    )
    volume = global_metric(np.ones(len(ordered_keys), dtype=bool))
    interface = global_metric(interface_mask)
    return {
        "schema_version": "task035b.regionwise-p-field-comparison.v1",
        "status": "measured_common_native_visualization_points",
        "method": (
            "complex E vector relative L2 on the exact coordinate intersection "
            "of each MPI rank's native p5, p6, and candidate VTU shards"
        ),
        "interface_selection": {
            "substrate_plane_z_nm": interface_z,
            "grating_top_z_nm": grating_z_max,
            "grating_sidewalls_x_nm": [grating_x_min, grating_x_max],
            "coordinate_tolerance_nm": coordinate_tolerance,
        },
        "no_threshold_relaxation": True,
        "volume_selected_points": volume,
        "material_interface_selected_points": interface,
        "field_shard_authorities": shard_hashes,
        "pass": volume.get("pass") is True and interface.get("pass") is True,
    }


def run_target_regionwise_p_candidate(
    out_dir: Path,
    *,
    classifier_record: Path,
    classifier_sha256: str,
    control_record: Path,
    control_sha256: str,
    h_nm: float = 10.0,
    incident_theta_deg: float = 80.0,
    polarization_kind: str = "s",
    progress_observer=None,
) -> dict[str, Any]:
    """Run one p4-trace, classifier-selected p4/p6-interior candidate."""

    from src.adaptivity.high_order_resource_audit import (
        build_high_order_resource_audit,
    )
    from src.common.config_3d import target_stage4_config
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    classifier_record = Path(classifier_record).resolve()
    control_record = Path(control_record).resolve()
    if _sha256(classifier_record) != str(classifier_sha256):
        raise ValueError("Task035b classifier SHA256 authority mismatch")
    if _sha256(control_record) != str(control_sha256):
        raise ValueError("Task035b p5/p6 control SHA256 authority mismatch")
    classifier = json.loads(classifier_record.read_text(encoding="utf-8"))
    control = json.loads(control_record.read_text(encoding="utf-8"))
    p5 = control.get("coarse") or {}
    p6 = control.get("enriched") or {}
    if p5.get("degree") != 5 or p6.get("degree") != 6:
        raise ValueError("Task035b control record is not a p5/p6 pair")
    control_run_dir = Path(control["raw_evidence"]["run_directory"])
    if not control_run_dir.is_absolute():
        control_run_dir = Path(__file__).resolve().parents[2] / control_run_dir
    required_control_artifacts = [
        control_run_dir / degree_dir / "dtn_port_diffraction_orders_3d.json"
        for degree_dir in ("coarse_p5", "enriched_p6")
    ]
    required_control_artifacts.extend(
        control_run_dir
        / degree_dir
        / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
        for degree_dir in ("coarse_p5", "enriched_p6")
        for rank in range(8)
    )
    missing_control_artifacts = [
        str(path) for path in required_control_artifacts if not path.is_file()
    ]
    if missing_control_artifacts:
        raise ValueError(
            "Task035b p5/p6 raw field/channel authorities are incomplete: "
            + ", ".join(missing_control_artifacts)
        )
    if (
        classifier.get("pass") is not True
        or classifier.get("geometry")
        != "Task034 fixed rectangular block grating"
        or classifier.get("cell_count") != 252
    ):
        raise ValueError("Task035b classifier authority is not qualified")
    actions = (classifier.get("classifier") or {}).get(
        "local_order_actions"
    ) or []
    high_ids = tuple(
        int(entry["canonical_cell_id"])
        for entry in actions
        if entry.get("action") == "p_up"
    )
    budget = classifier.get(
        "candidate_fixed_p4_trace_regionwise_p6_interior_dof_budget"
    ) or {}
    if (
        len(high_ids) != int(budget.get("high_interior_cells", -1))
        or budget.get("active_full3d_equivalent_dofs") != 88994
    ):
        raise ValueError("classifier actions and regionwise-p DoF budget disagree")
    base = target_stage4_config(degree=6, h_nm=float(h_nm))
    cfg = replace(
        base,
        case_name=(
            f"task035b_regionwise_p4trace_p6interior_h{h_nm:g}"
        ).replace(".", "p"),
        incident_theta_deg=float(incident_theta_deg),
        polarization_kind=polarization_kind,
        custom_polarization=None,
        mesh_cell_type="hexahedron",
        nedelec_trace_degree=4,
        nedelec_interior_degree=6,
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        full3d_reference_export=False,
        direct_release_base_after_augmentation=True,
        stage4_cell_static_condensation=True,
        stage4_assembly_time_cell_static_condensation=True,
        stage4_floquet_slave_elimination=True,
        stage4_regionwise_interior_p=True,
        stage4_regionwise_high_canonical_cell_ids=high_ids,
        stage4_regionwise_mesh_geometry_sha256=str(
            classifier["mesh_geometry_sha256"]
        ),
        direct_release_solver_before_postprocess=True,
        petsc_extra_options={
            **base.petsc_extra_options,
            "mat_mumps_icntl_14": 100,
        },
        unique_output=False,
    )
    capture: dict[str, Any] = {}

    def observer(**state):
        capture.update(
            field=state["field"],
            mesh_data=state["mesh_data"],
        )

    def progress(stage: str, status: str) -> None:
        if progress_observer is not None:
            progress_observer(stage, status)

    progress("regionwise_p_candidate_solve", "begin")
    started = time.perf_counter()
    summary = run_stage4b_block_grating_3d_case(
        cfg,
        out_dir / "candidate",
        solution_observer=observer,
    )
    progress("regionwise_p_candidate_solve", "end")
    if summary.get("official_result") is not True:
        raise RuntimeError("regionwise-p candidate did not produce an official result")
    resource_audit = build_high_order_resource_audit(
        capture["field"],
        capture["mesh_data"],
        summary,
    )
    cell_audit = summary.get("cell_static_condensation") or {}
    if (
        cell_audit.get("regionwise_mesh_geometry_sha256")
        != classifier["mesh_geometry_sha256"]
        or cell_audit.get("regionwise_high_cell_count") != len(high_ids)
        or cell_audit.get("active_full3d_equivalent_dofs") != 88994
    ):
        raise RuntimeError("regionwise-p actual solve identity/budget did not close")
    observable_comparison = _observable_comparison(summary, p5, p6)
    channel_comparison = _channel_comparison(
        p5_dir=control_run_dir / "coarse_p5",
        p6_dir=control_run_dir / "enriched_p6",
        candidate_dir=out_dir / "candidate",
    )
    progress("regionwise_p_field_interface_comparison", "begin")
    field_interface_comparison = _selected_field_interface_comparison(
        p5_dir=control_run_dir / "coarse_p5",
        p6_dir=control_run_dir / "enriched_p6",
        candidate_dir=out_dir / "candidate",
    )
    progress("regionwise_p_field_interface_comparison", "end")
    residual = summary.get("linear_system_relative_residual")
    execution_pass = bool(
        isinstance(residual, (int, float))
        and float(residual) <= 1.0e-9
        and (resource_audit.get("entity_dof_inventory") or {}).get("pass")
        is True
        and summary.get("mesh_cell_type_actual") == "hexahedron"
    )
    accuracy_pass = bool(
        observable_comparison["all_scalar_same_code_bands_pass"]
        and observable_comparison["normalized_R_T_Aclosure_vector_pass"]
        and channel_comparison["pass"]
        and field_interface_comparison["pass"]
    )
    return {
        "schema_version": "task035b.regionwise-p-candidate.v1",
        "status": (
            "actual_regionwise_p_candidate_pass"
            if execution_pass and accuracy_pass
            else "actual_regionwise_p_controlled_negative"
            if execution_pass
            else "actual_regionwise_p_execution_fail"
        ),
        "pass": execution_pass,
        "candidate_accuracy_pass": accuracy_pass,
        "ordinary_default_changed": False,
        "target_identity": {
            "geometry": "Task034 fixed rectangular block grating",
            "h_nm": float(h_nm),
            "mesh_geometry_sha256": classifier["mesh_geometry_sha256"],
            "trace_degree": 4,
            "low_interior_degree": 4,
            "high_interior_degree": 6,
        },
        "classifier_authority": {
            "path": str(classifier_record),
            "sha256": classifier_sha256,
            "high_canonical_cell_count": len(high_ids),
            "active_full3d_equivalent_dofs": 88994,
        },
        "control_authority": {
            "path": str(control_record),
            "sha256": control_sha256,
        },
        "candidate": {
            "degree": 6,
            "h_nm": float(h_nm),
            "summary": summary,
            "high_order_resource_audit": resource_audit,
        },
        "observable_comparison": observable_comparison,
        "diffraction_channel_comparison": channel_comparison,
        "selected_field_interface_error_gate": field_interface_comparison,
        "elapsed_seconds": float(time.perf_counter() - started),
    }


__all__ = ["run_target_regionwise_p_candidate"]
