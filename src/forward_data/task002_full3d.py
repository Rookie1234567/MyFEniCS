"""Parameterized, fixed-topology Full3D production route for Task002 M2C."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    SimulationConfig3D,
    target_stage4_config,
)
from src.common.modes_3d import enumerate_diffraction_orders_3d
from src.geometry.mesh_builder_3d import stage4_axis_plan

from .orders import FIXED_M_ORDERS, POLARIZATIONS, extract_fixed_orders
from .provenance import canonical_hash
from .task002_campaign import formal_preflight
from .task002_schema import Task002ForwardParameters
from .watchdog import WatchdogResult, run_with_watchdog


TASK002_FULL3D_RECORD_SCHEMA = "task002.full3d-record.v1"
TASK002_FULL3D_TOPOLOGY_SCHEMA = "task002.full3d-topology.v1"
AXIS_CELL_COUNTS = (6, 3, 14)
LAYER_CELL_COUNTS = (1, 12, 1)


def build_task002_full3d_config(parameters: Task002ForwardParameters) -> SimulationConfig3D:
    """Build the formal Full3D config with fixed logical topology."""

    parameters.validate()
    fidelity = parameters.fidelity
    cfg = target_stage4_config(degree=int(fidelity["degree"]), h_nm=10.0)
    cfg.grating_height = float(parameters.height_nm)
    cfg.grating_width_x = float(parameters.width_x_nm)
    cfg.incident_theta_deg = float(parameters.theta_deg)
    cfg.incident_phi_deg = float(parameters.phi_deg)
    cfg.polarization_kind = "s"
    cfg.nedelec_trace_degree = None
    cfg.nedelec_interior_degree = None
    cfg.mesh_axis_cell_counts = AXIS_CELL_COUNTS
    cfg.mesh_spacing_mode = "boundary_fitted"
    substrate_cells, grating_cells, air_cells = LAYER_CELL_COUNTS
    substrate = [
        cfg.domain_z_min + i * (cfg.interface_z - cfg.domain_z_min) / substrate_cells
        for i in range(substrate_cells + 1)
    ]
    grating = [
        cfg.interface_z + i * (cfg.grating_z_max - cfg.interface_z) / grating_cells
        for i in range(1, grating_cells + 1)
    ]
    air = [
        cfg.grating_z_max + i * (cfg.domain_z_max - cfg.grating_z_max) / air_cells
        for i in range(1, air_cells + 1)
    ]
    cfg.mesh_axis_z_values = tuple(substrate + grating + air)
    cfg.mesh_axis_z_profile = "task002-full3d-fixed-layers-1-12-1"
    cfg.mesh_cell_type = "hexahedron"
    cfg.stage4_full3d_assembly_backend = ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
    cfg.matrix_diagnostics_assemble_only = False
    cfg.unique_output = False
    cfg.case_name = (
        f"task002_full3d_p{fidelity['degree']}_h10_hgt{parameters.height_nm:g}_"
        f"wid{parameters.width_x_nm:g}_theta{parameters.theta_deg:g}_"
        f"phi{parameters.azimuth_deg:g}_s"
    ).replace(".", "p")
    return cfg


def task002_full3d_config_identity(
    parameters: Task002ForwardParameters,
) -> dict[str, Any]:
    """Return the deterministic, JSON-safe numerical configuration authority."""

    cfg = build_task002_full3d_config(parameters)
    identity = {
        "solver_route_id": parameters.fidelity["solver_route_id"],
        "element": _element_identity(int(cfg.nedelec_degree)),
        "mesh": {
            "cell_type": cfg.mesh_cell_type,
            "spacing_mode": cfg.mesh_spacing_mode,
            "axis_cell_counts": list(cfg.mesh_axis_cell_counts_requested or ()),
            "axis_z_values_nm": list(cfg.mesh_axis_z_values or ()),
            "axis_z_profile": cfg.mesh_axis_z_profile,
            "target_h_nm": float(cfg.mesh_target_size),
        },
        "geometry": {
            "height_nm": float(cfg.grating_height),
            "width_x_nm": float(cfg.grating_width_x),
        },
        "illumination": {
            "wavelength_nm": float(cfg.lambda0), "polarization": "S",
            "theta_deg": float(cfg.incident_theta_deg),
            "phi_deg": float(cfg.incident_phi_deg),
            "grazing_deg": float(parameters.grazing_deg),
            "azimuth_deg": float(parameters.azimuth_deg),
        },
        "assembly_backend": ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        "mpi_ranks": 2, "threads_per_rank": 1,
    }
    return {**identity, "config_sha256": canonical_hash(identity)}


def _logical_cells(counts: tuple[int, int, int]) -> list[list[int]]:
    nx, ny, nz = counts

    def node(i: int, j: int, k: int) -> int:
        return i + (nx + 1) * (j + (ny + 1) * k)

    return [
        [
            node(i, j, k), node(i + 1, j, k), node(i, j + 1, k),
            node(i + 1, j + 1, k), node(i, j, k + 1),
            node(i + 1, j, k + 1), node(i, j + 1, k + 1),
            node(i + 1, j + 1, k + 1),
        ]
        for k in range(nz) for j in range(ny) for i in range(nx)
    ]


def _sha_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _element_identity(degree: int) -> dict[str, Any]:
    from basix.ufl import element

    ufl_element = element("N1curl", "hexahedron", degree, dtype=np.float64)
    signature = str(ufl_element)
    return {
        "family": "N1curl", "cell": "hexahedron", "degree": degree,
        "nedelec_fixed_trace_enabled": False,
        "resolved_trace_degree": degree, "resolved_interior_degree": degree,
        "actual_ufl_basix_element_signature": signature,
        "element_signature_sha256": hashlib.sha256(signature.encode()).hexdigest(),
    }


def task002_full3d_topology_identity(
    parameters: Task002ForwardParameters, *, comm_size: int = 2,
) -> dict[str, Any]:
    cfg = build_task002_full3d_config(parameters)
    plan = stage4_axis_plan(cfg, comm_size)
    axes = {
        "x": np.asarray(plan.x_values, dtype=np.float64),
        "y": np.asarray(plan.y_values, dtype=np.float64),
        "z": np.asarray(plan.z_values, dtype=np.float64),
    }
    counts = tuple(len(axes[name]) - 1 for name in ("x", "y", "z"))
    cells = _logical_cells(counts)
    tags = []
    nx, ny, nz = counts
    for k, z in enumerate(0.5 * (axes["z"][:-1] + axes["z"][1:])):
        for j, _y in enumerate(0.5 * (axes["y"][:-1] + axes["y"][1:])):
            for i, x in enumerate(0.5 * (axes["x"][:-1] + axes["x"][1:])):
                cell_id = i + nx * (j + ny * k)
                if z < cfg.interface_z:
                    tag = cfg.tags.substrate
                elif cfg.grating_x_min < x < cfg.grating_x_max and z < cfg.grating_z_max:
                    tag = cfg.tags.grating
                else:
                    tag = cfg.tags.air
                tags.append([cell_id, tag])
    floquet = {
        "x_pairs": [[j, k] for k in range(nz) for j in range(ny)],
        "y_pairs": [[i, k] for k in range(nz) for i in range(nx)],
    }
    element = _element_identity(int(cfg.nedelec_degree))
    topology_hash = _sha_json(cells)
    material_hash = _sha_json(tags)
    floquet_hash = _sha_json(floquet)
    dof_layout = _sha_json({
        "logical_topology_sha256": topology_hash,
        "element_signature_sha256": element["element_signature_sha256"],
        "floquet_entity_topology_sha256": floquet_hash,
    })
    return {
        "schema_version": TASK002_FULL3D_TOPOLOGY_SCHEMA,
        "axis_cell_counts": list(counts), "cell_count": int(np.prod(counts)),
        "logical_connectivity_sha256": topology_hash,
        "material_tag_topology_sha256": material_hash,
        "floquet_entity_topology_sha256": floquet_hash,
        "dof_layout_identity_sha256": dof_layout,
        "resolved_axes_nm": {name: values.tolist() for name, values in axes.items()},
        "coordinate_sha256": hashlib.sha256(
            b"".join(axes[name].astype("<f8", copy=False).tobytes()
                     for name in ("x", "y", "z"))
        ).hexdigest(),
        "material_region_cell_counts": {
            "air": sum(tag == cfg.tags.air for _, tag in tags),
            "substrate": sum(tag == cfg.tags.substrate for _, tag in tags),
            "grating": sum(tag == cfg.tags.grating for _, tag in tags),
        },
        "material_plane_alignment": bool(plan.material_plane_alignment["all_aligned"]),
        "positive_axis_widths": all(np.all(np.diff(values) > 0) for values in axes.values()),
        "element_identity": element,
        "topology_element_hash": canonical_hash({
            "connectivity": topology_hash, "material_tags": material_hash,
            "floquet": floquet_hash, "dof_layout": dof_layout,
        }),
        "config_identity": task002_full3d_config_identity(parameters),
    }


def extract_task002_full3d_orders(
    rows: list[dict[str, Any]], *, parameters: Task002ForwardParameters,
    port_power: dict[str, Any],
) -> dict[str, Any]:
    cfg = build_task002_full3d_config(parameters)
    analytic = {
        (order.m, order.n): order
        for order in enumerate_diffraction_orders_3d(
            cfg, max_m_override=max(abs(v) for v in FIXED_M_ORDERS), max_n_override=0,
        )
    }
    expected_nonpropagating = set()
    wavevectors = {}
    for m in FIXED_M_ORDERS:
        order = analytic[(m, 0)]
        for side, propagating in (("top", order.top_propagating),
                                  ("bottom", order.bottom_propagating)):
            beta = order.beta_top if side == "top" else order.beta_bottom
            wavevectors[(side, m, 0)] = {
                "kx": order.alpha, "ky": order.gamma,
                "kz": beta if side == "top" else -beta,
            }
            if not propagating:
                expected_nonpropagating.update(
                    (side, m, 0, polarization) for polarization in POLARIZATIONS
                )
    return extract_fixed_orders(
        rows, port_power=port_power,
        expected_nonpropagating=expected_nonpropagating,
        incident_polarization="S", wavevectors=wavevectors,
    )


def task002_full3d_command(
    *, root: Path, parameters_file: Path, baseline_sha: str, output_dir: Path,
) -> list[str]:
    return [
        "mpiexec", "-n", "2", str(root / ".venv/bin/python"),
        "-m", "src.runners.run_task002_full3d",
        "--parameters-json", str(parameters_file),
        "--baseline-sha", baseline_sha, "--output-dir", str(output_dir),
    ]


def run_formal_task002_full3d(
    parameters: Task002ForwardParameters, *, root: Path, baseline_sha: str,
    run_directory: Path, timeout_seconds: float,
) -> tuple[WatchdogResult, Path]:
    parameters.validate()
    preflight = formal_preflight(root, baseline_sha)
    run_directory.mkdir(parents=True, exist_ok=False)
    parameters_path = run_directory / "parameters.json"
    parameters_path.write_text(
        json.dumps(asdict(parameters), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result_dir = run_directory / "results"
    command = task002_full3d_command(
        root=root, parameters_file=parameters_path, baseline_sha=baseline_sha,
        output_dir=result_dir,
    )
    env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
    result = run_with_watchdog(
        command, cwd=root, env=env, output_dir=run_directory / "watchdog",
        timeout_seconds=timeout_seconds,
        memory_limit_bytes=preflight["resources"]["hard_ceiling_bytes"],
    )
    execution = {
        "schema_version": "task002.full3d-execution.v1",
        "parameters": parameters.as_dict(), "baseline_sha": baseline_sha,
        "parameter_hash": canonical_hash(parameters.as_dict()),
        "preflight": preflight, "command": command, "watchdog": asdict(result),
        "formal_record_present": (result_dir / "task002_full3d_record.json").is_file(),
    }
    execution_path = run_directory / "execution.json"
    execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    return result, execution_path


def formal_record_status(run_directory: Path, result: WatchdogResult) -> str:
    record = run_directory / "results/task002_full3d_record.json"
    if record.is_file():
        gates = json.loads(record.read_text(encoding="utf-8"))["gates"]
        return "measured_pass" if all(gates.values()) else "failed_numerical_gate"
    return "controlled_stop_resource" if "memory" in result.status.lower() else "failed_numerical_gate"
